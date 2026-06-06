from __future__ import annotations

import re
from datetime import date

import pandas as pd

from .client import LLMClient
from .models import AlertAnalysis
from .watch_analyst import conclusion_from_text


def _extract_price(text: str, labels: tuple[str, ...]) -> float | None:
    for label in labels:
        match = re.search(rf"{label}[^\d]*(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


class AlertAnalyst:
    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()

    def analyze(self, holding: dict, klines: pd.DataFrame) -> AlertAnalysis:
        latest = klines.tail(20).to_dict("records")
        content = self.client.invoke(
            [
                {"role": "system", "content": "你是A股中长线持仓管理助手，输出持有/注意/建议卖出和简短理由。"},
                {"role": "user", "content": f"分析持仓：{holding}，最近行情={latest}。如建议调整止损或目标价，请明确写出数值。"},
            ]
        )
        return AlertAnalysis(
            code=holding["code"],
            conclusion=conclusion_from_text(content),
            content=content,
            analysis_date=date.today().isoformat(),
            suggested_stop_loss=_extract_price(content, ("止损", "stop")),
            suggested_take_profit=_extract_price(content, ("目标", "止盈", "target")),
        )

