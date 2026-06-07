from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Static

from stocktools.cli.cmd_find import format_indicator_summary
from stocktools.scanners.registry import scanner_names
from stocktools.tui.stock_style import stock_name_cell
from stocktools.tui.widgets.detail_panel import DetailPanel


class _ScanResultsTable(DataTable):
    """DataTable that does not bind left/right so arrows can switch scanners."""

    BINDINGS = [
        Binding("enter", "select_cursor", show=False),
        Binding("up", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
        Binding("pageup", "page_up", show=False),
        Binding("pagedown", "page_down", show=False),
        Binding("ctrl+home", "scroll_top", show=False),
        Binding("ctrl+end", "scroll_bottom", show=False),
        Binding("home", "scroll_home", show=False),
        Binding("end", "scroll_end", show=False),
    ]


class ScanTab(Widget):

    HINTS = "Enter:加入关注池  空格:执行扫描  ←→:切换扫描器  c:导出CSV"

    def __init__(self) -> None:
        super().__init__()
        self._results: list[dict] = []
        self._scanners = scanner_names()
        self._scanner_idx: int = 0
        self._selected_scanner: str = self._scanners[0]

    def compose(self) -> ComposeResult:
        with Horizontal(id="content"):
            with Vertical(id="left-panel"):
                yield Static("", id="scanner-selector")
                yield _ScanResultsTable(id="scan-results")
            yield DetailPanel()
        yield Static(
            "[bright_blue]空格[/]执行扫描  [bright_blue]←→[/]切换扫描器  "
            "[bright_blue]Enter[/]加入关注池  [bright_blue]c[/]导出CSV",
            classes="page-hints",
        )

    def on_mount(self) -> None:
        table = self.query_one("#scan-results", DataTable)
        table.cursor_type = "row"
        table.add_columns("代码", "名称", "形态", "关键指标")
        self._render_scanner_bar()

    def _render_scanner_bar(self) -> None:
        parts = ["[bold]扫描器:[/]\n"]
        for i, name in enumerate(self._scanners):
            if i == self._scanner_idx:
                parts.append(f"[bold bright_blue underline] {name} [/]")
            else:
                parts.append(f"[dim] {name} [/]")
        self.query_one("#scanner-selector", Static).update(" ".join(parts))
        self._selected_scanner = self._scanners[self._scanner_idx]

    def select_prev_scanner(self) -> None:
        self._scanner_idx = (self._scanner_idx - 1) % len(self._scanners)
        self._render_scanner_bar()

    def select_next_scanner(self) -> None:
        self._scanner_idx = (self._scanner_idx + 1) % len(self._scanners)
        self._render_scanner_bar()

    def run_scan(self) -> None:
        self.query_one(DetailPanel).set_loading("扫描中...")
        table = self.query_one("#scan-results", DataTable)
        table.clear()
        self._results = []
        self.run_worker(self._do_scan(), exclusive=True)

    async def _do_scan(self) -> None:
        svc = self.app._find_svc
        scanner_name = self._selected_scanner
        try:
            await asyncio.to_thread(self._scan_in_thread, svc, scanner_name)
        except Exception as e:
            self.app.notify(str(e), severity="error")
        self._finish_scan()

    def _scan_in_thread(self, svc, scanner_name: str) -> None:
        for item in svc.iter_scan(scanner_name):
            self.app.call_from_thread(self._append_scan_result, item)

    def _append_scan_result(self, item: dict) -> None:
        table = self.query_one("#scan-results", DataTable)
        is_first = not self._results
        self._results.append(item)
        table.add_row(
            item["code"],
            stock_name_cell(self.app._find_svc.kline_repo, item["code"], item.get("name", "")),
            item.get("pattern", ""),
            format_indicator_summary(item, limit=2),
            key=item["code"],
        )
        if is_first:
            table.move_cursor(row=0)
            self._show_detail(0)

    def _finish_scan(self) -> None:
        detail = self.query_one(DetailPanel)
        if self._results:
            self.app.notify(f"扫描完成，共 {len(self._results)} 条")
        else:
            detail.clear()
            detail.set_loading("未发现匹配股票")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.cursor_row is not None and event.cursor_row < len(self._results):
            self._show_detail(event.cursor_row)

    def _show_detail(self, idx: int) -> None:
        item = self._results[idx]
        in_watchlist = self.app._record_svc.show(item["code"]) is not None
        self.query_one(DetailPanel).render_scan_detail(item, in_watchlist)

    def selected_item(self) -> dict | None:
        table = self.query_one("#scan-results", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self._results):
            return self._results[table.cursor_row]
        return None

    def refresh_data(self) -> None:
        self.run_scan()
