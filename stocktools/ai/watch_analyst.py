from __future__ import annotations

import re
from datetime import date

import pandas as pd

from .client import LLMClient
from .models import WatchAnalysis

SYSTEM_PROMPT = """\
你是A股中长线交易助手。根据用户提供的股票信息和近期行情数据，给出详细分析和操作建议。

你必须严格按照以下格式回复，不要添加任何额外内容：

analysis: <你的详细分析，包括趋势判断、量价关系、支撑压力位、风险点等，写在一行内>
conclusion: <buy|wait|hold|sell 四选一>

字段说明：
- analysis: 对该股票当前走势的完整分析，一段话写完，不要换行
- conclusion: 你的操作建议，只能从 buy/wait/hold/sell 中选一个
  - buy: 当前适合买入
  - wait: 还需观察，暂不操作
  - hold: 已持有的继续持有
  - sell: 建议卖出或回避\
"""

USER_PROMPT_TEMPLATE = """\
请分析以下股票：
- 代码：{code}
- 名称：{name}
- 已识别形态：{patterns}
- 最近30个交易日行情：
{klines}\
"""


def parse_response(text: str) -> tuple[str, str]:
    analysis = ""
    conclusion = "wait"

    m = re.search(r"^analysis:\s*(.+)", text, re.MULTILINE)
    if m:
        analysis = m.group(1).strip()

    m = re.search(r"^conclusion:\s*(\S+)", text, re.MULTILINE)
    if m:
        raw = m.group(1).strip().lower()
        if raw in ("buy", "wait", "hold", "sell"):
            conclusion = raw

    if not analysis:
        analysis = text.strip()

    return analysis, conclusion


class WatchAnalyst:
    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()

    def analyze(self, code: str, name: str, patterns: str | None, klines: pd.DataFrame, user_prompt: str = "") -> WatchAnalysis:
        klines_str = klines.tail(30).to_csv(index=False)
        prompt = USER_PROMPT_TEMPLATE.format(
            code=code,
            name=name,
            patterns=patterns or "无",
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
        analysis, conclusion = parse_response(content)
        return WatchAnalysis(code=code, conclusion=conclusion, content=analysis, analysis_date=date.today().isoformat())

