from __future__ import annotations

import json
from datetime import date

import pandas as pd

from .client import LLMClient
from .features import compute_features
from .models import AlertAnalysis
from .watch_analyst import _loads_json

SYSTEM_PROMPT = """\
你是A股中长线持仓管理助手。用户已做多持股，你需要根据中性行情特征分析持仓状况，并给出止损线和止盈线建议。

只输出 JSON，不要输出 markdown 或额外解释。JSON schema:
{
  "stop_loss": 12.50,
  "take_profit": 18.00,
  "analysis": "一段分析"
}
"""

USER_PROMPT_TEMPLATE = """\
请分析以下持仓：
- 代码：{code}
- 名称：{name}
- 买入价：{cost_price}
- 中性行情特征：
{features}
"""


def holding_cost_price(holding: dict) -> object:
    cost_price = holding.get("cost_price")
    if cost_price is None:
        cost_price = holding.get("entry_price")
    if cost_price is None:
        return "未知"
    return cost_price


class AlertAnalyst:
    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()

    def analyze(self, holding: dict, klines: pd.DataFrame, user_prompt: str = "") -> AlertAnalysis:
        prompt = USER_PROMPT_TEMPLATE.format(
            code=holding.get("code", ""),
            name=holding.get("name", ""),
            cost_price=holding_cost_price(holding),
            features=json.dumps(compute_features(klines), ensure_ascii=False, indent=2),
        )
        if user_prompt:
            prompt = f"{prompt}\n\n用户补充：{user_prompt}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        raw = _invoke_json(self.client, messages)
        parsed = _parse_alert(raw)
        if parsed is None:
            retry_messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "上次输出无法解析为合法 JSON。请只输出 JSON，必须包含正数 stop_loss、take_profit 和 analysis。"},
            ]
            raw = _invoke_json(self.client, retry_messages)
            parsed = _parse_alert(raw)
        if parsed is None:
            return AlertAnalysis(
                code=holding["code"],
                conclusion="止损：None；止盈：None",
                content=raw.strip() or "AI 输出无法解析，未给出有效止损止盈。",
                analysis_date=date.today().isoformat(),
                degraded=True,
            )
        return AlertAnalysis(
            code=holding["code"],
            conclusion=f"止损：{parsed['stop_loss']}；止盈：{parsed['take_profit']}",
            content=parsed["analysis"],
            analysis_date=date.today().isoformat(),
            suggested_stop_loss=parsed["stop_loss"],
            suggested_take_profit=parsed["take_profit"],
            degraded=False,
        )


def _invoke_json(client, messages: list[dict[str, str]]) -> str:
    try:
        return client.invoke(messages, response_format={"type": "json_object"})
    except TypeError:
        return client.invoke(messages)


def _parse_alert(text: str) -> dict | None:
    payload = _loads_json(text)
    if not isinstance(payload, dict):
        return None
    analysis = str(payload.get("analysis", "")).strip()
    try:
        stop_loss = float(payload.get("stop_loss"))
        take_profit = float(payload.get("take_profit"))
    except (TypeError, ValueError):
        return None
    if stop_loss <= 0 or take_profit <= 0 or not analysis:
        return None
    return {"stop_loss": stop_loss, "take_profit": take_profit, "analysis": analysis}
