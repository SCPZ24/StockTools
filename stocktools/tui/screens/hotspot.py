from __future__ import annotations

from collections import OrderedDict

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Static


def _pct_cell(value: float) -> Text:
    style = "#e60012" if value > 0 else "#009900" if value < 0 else "white"
    sign = "+" if value > 0 else ""
    return Text(f"{sign}{value:.2f}%", style=style)


class HotspotTab(Widget):

    HINTS = "↑↓:滚动  PageUp/PageDown:翻页"

    def __init__(self) -> None:
        super().__init__()
        self._rankings: list[dict] = []
        self._hotspots: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="hotspot-content"):
            yield Static("[bold bright_blue]每日概念涨幅前 10[/]", id="hotspot-title")
            yield DataTable(id="hotspot-rankings")
            yield Static("", id="hotspot-summary", markup=True)
        yield Static(
            "[bright_blue]↑↓[/]滚动  [bright_blue]PageUp/PageDown[/]翻页",
            classes="page-hints",
        )

    def on_mount(self) -> None:
        table = self.query_one("#hotspot-rankings", DataTable)
        table.cursor_type = "row"
        table.add_columns("日期", "排名", "概念", "涨幅")

    def refresh_data(self) -> None:
        service = self.app._get_concept_svc()
        self._rankings = service.hotspot_repo.get_recent_records(10)
        self._hotspots = service.hot()
        self._render_rankings()
        self._render_summary()

    def _render_rankings(self) -> None:
        table = self.query_one("#hotspot-rankings", DataTable)
        table.clear()
        grouped: OrderedDict[str, list[dict]] = OrderedDict()
        for row in self._rankings:
            grouped.setdefault(row["date"], []).append(row)

        for day, rows in grouped.items():
            for idx, row in enumerate(rows):
                table.add_row(
                    day if idx == 0 else "",
                    str(row.get("rank", "")),
                    row.get("name") or row.get("code", ""),
                    _pct_cell(float(row.get("pct_chg") or 0)),
                )

        if table.row_count:
            table.move_cursor(row=0)
        else:
            table.add_row("无数据", "", "", "")

    def _render_summary(self) -> None:
        if not self._hotspots:
            if not self._rankings:
                self.query_one("#hotspot-summary", Static).update(
                    "[bold bright_blue]短期热点概念[/]\n概念数据未初始化，请先运行 st update --force 或 st init"
                )
                return
            self.query_one("#hotspot-summary", Static).update("[bold bright_blue]短期热点概念[/]\n无")
            return
        lines = ["[bold bright_blue]短期热点概念[/]"]
        for item in self._hotspots:
            lines.append(
                f"{item['name']}  {item['reason']}  "
                f"上榜{item['listed_days']}天/连续{item['consecutive_days']}天  "
                f"10日{float(item['return_10d']):+.2f}%"
            )
        self.query_one("#hotspot-summary", Static).update("\n".join(lines))
