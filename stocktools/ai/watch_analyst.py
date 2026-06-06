from __future__ import annotations

from datetime import date

import pandas as pd

from .client import LLMClient
from .models import WatchAnalysis


def conclusion_from_text(text: str) -> str:
    head = (text.strip().splitlines() or [""])[0].lower()
    mapping = {"buy": "buy", "买": "buy", "wait": "wait", "观察": "wait", "hold": "hold", "持有": "hold", "sell": "sell", "卖": "sell"}
    for key, value in mapping.items():
        if key in head:
            return value
    return head[:20] or "wait"


class WatchAnalyst:
    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()

    def analyze(self, code: str, name: str, patterns: str | None, klines: pd.DataFrame) -> WatchAnalysis:
        latest = klines.tail(20).to_dict("records")
        content = self.client.invoke(
            [
                {"role": "system", "content": "你是A股中长线交易助手，只输出一句结论和简短理由。"},
                {
                    "role": "user",
                    "content": f"分析是否适合买入：{code} {name}，形态={patterns or '无'}，最近行情={latest}",
                },
            ]
        )
        return WatchAnalysis(code=code, conclusion=conclusion_from_text(content), content=content, analysis_date=date.today().isoformat())

