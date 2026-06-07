from __future__ import annotations

import re
from datetime import date

import pandas as pd

from .client import LLMClient
from .models import AlertAnalysis

SYSTEM_PROMPT = """\
你是A股中长线持仓管理助手。用户已做多持股，你需要根据当前行情分析持仓状况，并给出止损线和止盈线建议。

你的语言应该犀利且专业，并且足够详细。

你必须严格按照以下格式回复，不要添加任何额外内容：

analysis: <你的详细分析，包括当前趋势、支撑压力位、风险点、主力行为分析、主力意图猜测、机构资金动向、主力或机构持股量等有助于用户做投资决策内容，写在一行内>
conclusion: 止损：<数值>；止盈：<数值>

字段说明：
- analysis: 对该持仓当前状况的完整分析，一段话写完，不要换行
- conclusion: 止损和止盈价格，必须是具体数值（如 止损：12.50；止盈：18.00）\
"""

USER_PROMPT_TEMPLATE = """\
请分析以下持仓：
- 代码：{code}
- 名称：{name}
- 买入价：{cost_price}
- 最近20个交易日行情：
{klines}\
"""


def holding_cost_price(holding: dict) -> object:
    cost_price = holding.get("cost_price")
    if cost_price is None:
        cost_price = holding.get("entry_price")
    if cost_price is None:
        return "未知"
    return cost_price


def parse_response(text: str) -> tuple[str, float | None, float | None]:
    analysis = ""
    stop_loss = None
    take_profit = None

    m = re.search(r"^analysis[：:]\s*(.+)", text, re.MULTILINE)
    if m:
        analysis = m.group(1).strip()

    m = re.search(r"^conclusion[：:].*?止损[：:]\s*(\d+(?:\.\d+)?)", text, re.MULTILINE)
    if m:
        stop_loss = float(m.group(1))

    m = re.search(r"^conclusion[：:].*?止盈[：:]\s*(\d+(?:\.\d+)?)", text, re.MULTILINE)
    if m:
        take_profit = float(m.group(1))

    if not analysis:
        analysis = text.strip()

    return analysis, stop_loss, take_profit


class AlertAnalyst:
    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()

    def analyze(self, holding: dict, klines: pd.DataFrame, user_prompt: str = "") -> AlertAnalysis:
        klines_str = klines.tail(20).to_csv(index=False)
        prompt = USER_PROMPT_TEMPLATE.format(
            code=holding.get("code", ""),
            name=holding.get("name", ""),
            cost_price=holding_cost_price(holding),
            klines=klines_str,
        )
        if user_prompt:
            prompt = f"{prompt}\n\n用户补充：{user_prompt}"
        content = self.client.invoke(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
        analysis, stop_loss, take_profit = parse_response(content)
        return AlertAnalysis(
            code=holding["code"],
            conclusion=f"止损：{stop_loss}；止盈：{take_profit}",
            content=analysis,
            analysis_date=date.today().isoformat(),
            suggested_stop_loss=stop_loss,
            suggested_take_profit=take_profit,
        )
