from __future__ import annotations

import json
import re
from datetime import date

import pandas as pd

from .client import LLMClient
from .features import compute_features
from .models import WatchAnalysis

CONCLUSIONS = {"buy", "wait", "hold", "sell"}

SYSTEM_PROMPT = """\
你是A股中长线交易助手。根据用户提供的中性行情特征，给出详细分析和操作建议。

只输出 JSON，不要输出 markdown 或额外解释。JSON schema:
{
  "trend": "up | down | range",
  "conclusion": "buy | wait | hold | sell",
  "confidence": 0.0,
  "analysis": "一段分析"
}
"""

USER_PROMPT_TEMPLATE = """\
请分析以下股票：
- 代码：{code}
- 名称：{name}
- 中性行情特征：
{features}
"""


class WatchAnalyst:
    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()

    def analyze(self, code: str, name: str, patterns: str | None, klines: pd.DataFrame, user_prompt: str = "") -> WatchAnalysis:
        prompt = USER_PROMPT_TEMPLATE.format(
            code=code,
            name=name,
            features=json.dumps(compute_features(klines), ensure_ascii=False, indent=2),
        )
        if user_prompt:
            prompt = f"{prompt}\n\n用户补充：{user_prompt}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        raw = _invoke_json(self.client, messages)
        parsed = _parse_watch(raw)
        if parsed is None:
            retry_messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "上次输出无法解析为合法 JSON。请只输出符合 schema 的 JSON，必须包含 conclusion 和 analysis。"},
            ]
            raw = _invoke_json(self.client, retry_messages)
            parsed = _parse_watch(raw)
        if parsed is None:
            return WatchAnalysis(
                code=code,
                conclusion="wait",
                content=raw.strip() or "AI 输出无法解析，已降级为 wait。",
                analysis_date=date.today().isoformat(),
                confidence=0.0,
                degraded=True,
            )
        return WatchAnalysis(
            code=code,
            conclusion=parsed["conclusion"],
            content=parsed["analysis"],
            analysis_date=date.today().isoformat(),
            confidence=parsed.get("confidence"),
            degraded=False,
        )


def _invoke_json(client, messages: list[dict[str, str]]) -> str:
    try:
        return client.invoke(messages, response_format={"type": "json_object"})
    except TypeError:
        return client.invoke(messages)


def _parse_watch(text: str) -> dict | None:
    payload = _loads_json(text)
    if not isinstance(payload, dict):
        return None
    conclusion = str(payload.get("conclusion", "")).lower()
    analysis = str(payload.get("analysis", "")).strip()
    if conclusion not in CONCLUSIONS or not analysis:
        return None
    confidence = payload.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    return {"conclusion": conclusion, "analysis": analysis, "confidence": confidence}


def _loads_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            return None
    block = re.search(r"\{.*\}", text, re.S)
    if block:
        try:
            return json.loads(block.group(0))
        except json.JSONDecodeError:
            return None
    return None
