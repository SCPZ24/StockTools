from __future__ import annotations

import textwrap

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static


CONCLUSION_STYLE = {
    "buy": "bold bright_red",
    "sell": "bold bright_green",
    "hold": "bold bright_yellow",
    "wait": "bold dim",
}


def _wrap_content(text: str, width: int = 72) -> str:
    """Wrap a long text block, preserving existing newlines."""
    lines: list[str] = []
    for line in text.strip().splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
        else:
            for wrapped in textwrap.wrap(stripped, width=width):
                lines.append(f"  {wrapped}")
    return "\n".join(lines)


class DetailPanel(Widget):

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="right-panel"):
            yield Static("", id="detail-content", markup=True)

    def clear(self) -> None:
        self.query_one("#detail-content", Static).update("")

    def set_loading(self, message: str = "分析中...") -> None:
        self.query_one("#detail-content", Static).update(f"[dim italic]{message}[/]")

    def render_watchlist_detail(self, item: dict, ai_logs: list[dict]) -> None:
        parts: list[str] = []
        parts.append(f"[bold bright_blue]── 基本信息 ──[/]\n")
        parts.append(f"  代码    {item['code']}")
        parts.append(f"  名称    {item['name']}")
        if item.get("pattern"):
            parts.append(f"  形态    {item['pattern']}")
        parts.append(f"  加入日期  {item.get('added_at', '-')}")
        buy_flag = "是" if item.get("buy_tomorrow") else "否"
        if item.get("buy_tomorrow"):
            buy_flag = f"[bright_yellow]{buy_flag}[/]"
        parts.append(f"  明天买   {buy_flag}")

        if item.get("note"):
            parts.append(f"\n[bold bright_blue]── 备注 ──[/]\n")
            parts.append(_wrap_content(item["note"]))

        if ai_logs:
            parts.append(f"\n[bold bright_blue]── AI 买入分析 ──[/]")
            for log in ai_logs:
                cls = CONCLUSION_STYLE.get(log.get("conclusion", "").lower(), "")
                conclusion_markup = f"[{cls}]{log['conclusion']}[/]" if cls else log.get("conclusion", "-")
                parts.append(f"\n  [{log.get('analysis_date', '-')}]  结论: {conclusion_markup}")
                content = log.get("content", "")
                if content:
                    parts.append(_wrap_content(content))

        self.query_one("#detail-content", Static).update("\n".join(parts))

    def render_holding_detail(self, item: dict, ai_log: dict | None) -> None:
        parts: list[str] = []
        parts.append(f"[bold bright_blue]── 持仓信息 ──[/]\n")
        parts.append(f"  代码      {item['code']}")
        parts.append(f"  名称      {item['name']}")
        parts.append(f"  买入价    {item.get('entry_price', '-')}")
        parts.append(f"  买入日期  {item.get('entry_date', '-')}")
        parts.append(f"  止损价    {item.get('stop_loss') or '-'}")
        parts.append(f"  目标价    {item.get('take_profit') or '-'}")

        if item.get("note"):
            parts.append(f"\n[bold bright_blue]── 备注 ──[/]\n")
            parts.append(_wrap_content(item["note"]))

        if ai_log:
            parts.append(f"\n[bold bright_blue]── AI 卖出分析 ──[/]")
            cls = CONCLUSION_STYLE.get(ai_log.get("conclusion", "").lower(), "")
            conclusion_markup = f"[{cls}]{ai_log['conclusion']}[/]" if cls else ai_log.get("conclusion", "-")
            parts.append(f"\n  [{ai_log.get('analysis_date', '-')}]  结论: {conclusion_markup}")
            content = ai_log.get("content", "")
            if content:
                parts.append(_wrap_content(content))
            if ai_log.get("suggested_stop_loss") is not None:
                parts.append(f"  建议止损  {ai_log['suggested_stop_loss']}")
            if ai_log.get("suggested_take_profit") is not None:
                parts.append(f"  建议目标  {ai_log['suggested_take_profit']}")

        self.query_one("#detail-content", Static).update("\n".join(parts))

    def render_scan_detail(self, item: dict, in_watchlist: bool) -> None:
        parts: list[str] = []
        parts.append(f"[bold bright_blue]── 股票信息 ──[/]\n")
        parts.append(f"  代码    {item.get('code', '-')}")
        parts.append(f"  名称    {item.get('name', '-')}")
        wl_text = "[bright_green]已在关注池[/]" if in_watchlist else "[dim]不在关注池[/]"
        parts.append(f"  关注    {wl_text}")

        indicators = {k: v for k, v in item.items() if k not in ("code", "name", "pattern")}
        if indicators:
            parts.append(f"\n[bold bright_blue]── 形态指标 ──[/]\n")
            for k, v in indicators.items():
                if isinstance(v, float):
                    v = f"{v:.4f}"
                parts.append(f"  {k:<16} {v}")

        self.query_one("#detail-content", Static).update("\n".join(parts))
