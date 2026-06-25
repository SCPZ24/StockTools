from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import json
from statistics import median
from typing import Callable

import pandas as pd

from .alert_analyst import AlertAnalyst
from .models import AlertAnalysis, WatchAnalysis
from .watch_analyst import WatchAnalyst, _invoke_json, _loads_json


ProgressCallback = Callable[[dict], None]

_ARBITER_SYSTEM = """\
你是一位严谨的投资仲裁分析师。下面是多位分析师对同一标的的独立分析。
请把它们综合成一段连贯、不重复的中文总体概要，聚焦共识与关键依据；如存在分歧请简要点明。
只输出 JSON，不要 markdown：{"summary": "一段总体概要"}\
"""


class WatchEnsemble:
    is_ensemble = True

    def __init__(self, analyst: WatchAnalyst | None = None, samples: int = 5, rounds_max: int = 3):
        self.analyst = analyst or WatchAnalyst()
        self.samples = samples
        self.rounds_max = rounds_max

    def analyze(
        self,
        code: str,
        name: str,
        klines: pd.DataFrame,
        on_progress: ProgressCallback | None = None,
        user_prompt: str = "",
    ) -> WatchAnalysis:
        last_votes: list[WatchAnalysis] = []
        for round_no in range(1, self.rounds_max + 1):
            votes = self._collect_votes(code, name, klines, round_no, on_progress, user_prompt)
            if votes:
                last_votes = votes
            top_label, top_count = _top_label(votes)
            if top_label and top_count >= 4:
                return self._result(code, top_label, votes, top_count / self.samples, degraded=False)
        top_label, top_count = _top_label(last_votes)
        return self._result(code, top_label or "wait", last_votes, top_count / self.samples if self.samples else 0, degraded=True)

    def _collect_votes(
        self,
        code: str,
        name: str,
        klines: pd.DataFrame,
        round_no: int,
        on_progress: ProgressCallback | None,
        user_prompt: str,
    ) -> list[WatchAnalysis]:
        votes: list[WatchAnalysis] = []
        attempts = 0
        max_attempts = self.samples * 2
        with ThreadPoolExecutor(max_workers=self.samples) as executor:
            while len(votes) < self.samples and attempts < max_attempts:
                batch = min(self.samples - len(votes), max_attempts - attempts)
                futures = [
                    executor.submit(self.analyst.analyze, code, name, None, klines, user_prompt)
                    for _ in range(batch)
                ]
                attempts += batch
                for future in as_completed(futures):
                    try:
                        vote = future.result()
                    except Exception as exc:
                        vote = WatchAnalysis(code=code, conclusion="wait", content=str(exc), analysis_date=date.today().isoformat(), degraded=True)
                    if not vote.degraded:
                        votes.append(vote)
                    if on_progress is not None:
                        on_progress({"type": "sample", "code": code, "round": round_no, "done": min(len(votes), self.samples), "total": self.samples})
        return votes

    def _result(self, code: str, conclusion: str, votes: list[WatchAnalysis], confidence: float, degraded: bool) -> WatchAnalysis:
        content = _make_summary(self.analyst, votes, conclusion, degraded)
        return WatchAnalysis(
            code=code,
            conclusion=conclusion,
            content=content,
            analysis_date=date.today().isoformat(),
            confidence=round(confidence, 2),
            degraded=degraded,
            votes=json.dumps([vote.__dict__ for vote in votes], ensure_ascii=False),
        )


class AlertEnsemble:
    is_ensemble = True

    def __init__(self, analyst: AlertAnalyst | None = None, samples: int = 5, rounds_max: int = 3, tolerance: float = 0.06):
        self.analyst = analyst or AlertAnalyst()
        self.samples = samples
        self.rounds_max = rounds_max
        self.tolerance = tolerance

    def analyze(
        self,
        holding: dict,
        klines: pd.DataFrame,
        on_progress: ProgressCallback | None = None,
        user_prompt: str = "",
    ) -> AlertAnalysis:
        last_votes: list[AlertAnalysis] = []
        for round_no in range(1, self.rounds_max + 1):
            votes = self._collect_votes(holding, klines, round_no, on_progress, user_prompt)
            if votes:
                last_votes = votes
            decision = self._decide(votes)
            if decision and not decision["degraded"]:
                return self._build(holding["code"], votes, decision)
        decision = self._decide(last_votes, force_degraded=True)
        if decision:
            return self._build(holding["code"], last_votes, decision)
        return AlertAnalysis(
            code=holding["code"],
            conclusion="止损：None；止盈：None",
            content="没有获得有效 AI 票。",
            analysis_date=date.today().isoformat(),
            degraded=True,
            confidence=0.0,
            votes="[]",
        )

    def _collect_votes(
        self,
        holding: dict,
        klines: pd.DataFrame,
        round_no: int,
        on_progress: ProgressCallback | None,
        user_prompt: str,
    ) -> list[AlertAnalysis]:
        votes: list[AlertAnalysis] = []
        attempts = 0
        max_attempts = self.samples * 2
        with ThreadPoolExecutor(max_workers=self.samples) as executor:
            while len(votes) < self.samples and attempts < max_attempts:
                batch = min(self.samples - len(votes), max_attempts - attempts)
                futures = [executor.submit(self.analyst.analyze, holding, klines, user_prompt) for _ in range(batch)]
                attempts += batch
                for future in as_completed(futures):
                    try:
                        vote = future.result()
                    except Exception as exc:
                        vote = AlertAnalysis(holding["code"], "止损：None；止盈：None", str(exc), date.today().isoformat(), degraded=True)
                    if not vote.degraded and vote.suggested_stop_loss and vote.suggested_take_profit:
                        votes.append(vote)
                    if on_progress is not None:
                        on_progress({"type": "sample", "code": holding["code"], "round": round_no, "done": min(len(votes), self.samples), "total": self.samples})
        return votes

    def _decide(self, votes: list[AlertAnalysis], force_degraded: bool = False) -> dict | None:
        """纯代码裁定中位数与共识强度，不调用任何 LLM（避免每轮重复仲裁）。"""
        if not votes:
            return None
        stop_values = [float(v.suggested_stop_loss) for v in votes if v.suggested_stop_loss is not None]
        take_values = [float(v.suggested_take_profit) for v in votes if v.suggested_take_profit is not None]
        if not stop_values or not take_values:
            return None
        stop = float(median(stop_values))
        take = float(median(take_values))
        stop_count = _within_tol(stop_values, stop, self.tolerance)
        take_count = _within_tol(take_values, take, self.tolerance)
        degraded = force_degraded or stop_count < 4 or take_count < 4
        confidence = min(stop_count, take_count) / self.samples if self.samples else 0.0
        return {"stop": round(stop, 2), "take": round(take, 2), "degraded": degraded, "confidence": round(confidence, 2)}

    def _build(self, code: str, votes: list[AlertAnalysis], decision: dict) -> AlertAnalysis:
        conclusion = f"止损：{decision['stop']}；止盈：{decision['take']}"
        content = _make_summary(self.analyst, votes, conclusion, decision["degraded"])
        return AlertAnalysis(
            code=code,
            conclusion=conclusion,
            content=content,
            analysis_date=date.today().isoformat(),
            suggested_stop_loss=decision["stop"],
            suggested_take_profit=decision["take"],
            confidence=decision["confidence"],
            degraded=decision["degraded"],
            votes=json.dumps([vote.__dict__ for vote in votes], ensure_ascii=False),
        )


def _top_label(votes: list[WatchAnalysis]) -> tuple[str | None, int]:
    if not votes:
        return None, 0
    counter = Counter(vote.conclusion for vote in votes)
    priority = {"buy": 0, "hold": 1, "wait": 2, "sell": 3}
    label = sorted(counter, key=lambda item: (-counter[item], priority.get(item, 99), item))[0]
    return label, counter[label]


def _make_summary(analyst, votes: list, decision: str, degraded: bool) -> str:
    """共识/终态时由仲裁 agent 合成一段总体概要；无可用 client 或失败时回退为逐条拼接。"""
    if not votes:
        return "没有获得有效 AI 票。"
    client = getattr(analyst, "client", None)
    if client is not None:
        try:
            return _arbitrate(client, votes, decision, degraded)
        except Exception:
            pass
    return _summarize_votes(votes)


def _arbitrate(client, votes: list, decision: str, degraded: bool) -> str:
    analyses = "\n".join(f"{idx}. {getattr(vote, 'content', '')}" for idx, vote in enumerate(votes, start=1))
    note = "（分析师之间存在分歧，未达成强共识，请在概要中点明分歧并提示置信度偏低）" if degraded else ""
    user = f"综合裁定结论：{decision}{note}\n各独立分析：\n{analyses}\n请输出 JSON。"
    raw = _invoke_json(
        client,
        [
            {"role": "system", "content": _ARBITER_SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    payload = _loads_json(raw)
    summary = str(payload.get("summary", "")).strip() if isinstance(payload, dict) else ""
    if not summary:
        raise ValueError("仲裁未返回 summary")
    return summary


def _summarize_votes(votes: list[WatchAnalysis] | list[AlertAnalysis]) -> str:
    if not votes:
        return "没有获得有效 AI 票。"
    return "\n".join(f"{idx}. {vote.content}" for idx, vote in enumerate(votes, start=1))


def _within_tol(values: list[float], center: float, tolerance: float) -> int:
    if center == 0:
        return 0
    low = center * (1 - tolerance)
    high = center * (1 + tolerance)
    return sum(1 for value in values if low <= value <= high)
