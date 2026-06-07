from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import DataTable, Static

from stocktools.tui.widgets.detail_panel import DetailPanel


class WatchlistTab(Widget):

    HINTS = "a:添加  d:移除  g:明天买  n:备注  w:买入分析  Enter:转入持仓"

    def __init__(self) -> None:
        super().__init__()
        self._items: list[dict] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="content"):
            yield DataTable(id="left-panel")
            yield DetailPanel()
        yield Static(
            "[bright_blue]a[/]添加  [bright_blue]d[/]移除  [bright_blue]g[/]明天买  "
            "[bright_blue]n[/]备注  [bright_blue]w[/]买入分析  [bright_blue]Enter[/]转入持仓",
            classes="page-hints",
        )

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("名称", "明天买")

    def refresh_data(self) -> None:
        svc = self.app._record_svc
        self._items = svc.list_all()
        table = self.query_one(DataTable)
        table.clear()
        for item in self._items:
            buy_flag = "●" if item.get("buy_tomorrow") else ""
            table.add_row(item["name"], buy_flag, key=item["code"])
        if self._items:
            table.move_cursor(row=0)
            self._show_detail(0)
        else:
            self.query_one(DetailPanel).clear()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.cursor_row is not None and event.cursor_row < len(self._items):
            self._show_detail(event.cursor_row)

    def _show_detail(self, idx: int) -> None:
        item = self._items[idx]
        ai_logs = self.app._ai_logs_repo.get_recent(item["code"], "watch", 3)
        self.query_one(DetailPanel).render_watchlist_detail(item, ai_logs)

    def selected_item(self) -> dict | None:
        table = self.query_one(DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self._items):
            return self._items[table.cursor_row]
        return None
