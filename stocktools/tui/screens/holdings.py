from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import DataTable, Static

from stocktools.tui.widgets.detail_panel import DetailPanel


class HistoryModal(ModalScreen[None]):

    BINDINGS = [("escape", "dismiss", "关闭")]

    def __init__(self, records: list[dict]) -> None:
        super().__init__()
        self._records = records

    def compose(self):
        from textual.containers import Vertical
        with Vertical(id="history-container"):
            yield Static("[bold bright_blue]历史交易记录[/]", id="history-title")
            with VerticalScroll():
                yield DataTable(id="history-table")

    def on_mount(self) -> None:
        table = self.query_one("#history-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("名称", "买入价", "卖出价", "买入日期", "卖出日期")
        for r in self._records:
            table.add_row(
                r.get("name", "-"),
                str(r.get("entry_price", "-")),
                str(r.get("exit_price", "-")),
                r.get("entry_date", "-"),
                r.get("exit_date", "-"),
            )

    def action_dismiss(self) -> None:
        self.app.pop_screen()


class HoldingsTab(Widget):

    HINTS = "s:止损  t:目标  n:备注  x:平仓  r:减仓  A:分析  Shift+A:全部  h:历史"

    def __init__(self) -> None:
        super().__init__()
        self._items: list[dict] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="content"):
            yield DataTable(id="left-panel")
            yield DetailPanel()
        yield Static(
            "[bright_blue]s[/]止损价  [bright_blue]t[/]目标价  [bright_blue]n[/]备注  "
            "[bright_blue]x[/]平仓  [bright_blue]r[/]减仓  "
            "[bright_blue]A[/]卖出分析  [bright_blue]Shift+A[/]全部分析  [bright_blue]h[/]历史",
            classes="page-hints",
        )

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_column("名称")

    def refresh_data(self) -> None:
        svc = self.app._hold_svc
        self._items = svc.list_open()
        table = self.query_one(DataTable)
        table.clear()
        for item in self._items:
            table.add_row(item["name"], key=item["code"])
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
        ai_log = self.app._ai_logs_repo.get_latest(item["code"], "alert")
        self.query_one(DetailPanel).render_holding_detail(item, ai_log)

    def selected_item(self) -> dict | None:
        table = self.query_one(DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self._items):
            return self._items[table.cursor_row]
        return None
