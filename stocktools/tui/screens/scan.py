from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, DataTable, Static

from stocktools.scanners.registry import scanner_names
from stocktools.tui.widgets.detail_panel import DetailPanel


class ScanTab(Widget):

    HINTS = "Enter:加入关注池  空格:执行扫描  c:导出CSV"

    def __init__(self) -> None:
        super().__init__()
        self._results: list[dict] = []
        self._selected_scanner: str = scanner_names()[0]

    def compose(self) -> ComposeResult:
        with Horizontal(id="content"):
            with Vertical(id="left-panel"):
                with Horizontal(id="scanner-selector"):
                    for name in scanner_names():
                        cls = "scanner-btn selected" if name == self._selected_scanner else "scanner-btn"
                        yield Button(name, id=f"scan-{name}", classes=cls)
                yield DataTable(id="scan-results")
            yield DetailPanel()

    def on_mount(self) -> None:
        table = self.query_one("#scan-results", DataTable)
        table.cursor_type = "row"
        table.add_columns("代码", "名称", "形态", "关键指标")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("scan-"):
            scanner_name = event.button.id[5:]
            self._select_scanner(scanner_name)

    def _select_scanner(self, name: str) -> None:
        self._selected_scanner = name
        for btn in self.query(".scanner-btn"):
            btn.remove_class("selected")
        btn = self.query_one(f"#scan-{name}", Button)
        btn.add_class("selected")

    def run_scan(self) -> None:
        self.query_one(DetailPanel).set_loading("扫描中...")
        table = self.query_one("#scan-results", DataTable)
        table.clear()
        self._results = []
        self.run_worker(self._do_scan(), exclusive=True)

    async def _do_scan(self) -> None:
        svc = self.app._find_svc
        scanner_name = self._selected_scanner
        results = await self.app.run_in_thread(lambda: svc.scan(scanner_name))
        self._results = results
        table = self.query_one("#scan-results", DataTable)
        table.clear()
        for item in results:
            indicators = {k: v for k, v in item.items() if k not in ("code", "name", "pattern")}
            indicator_str = "  ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in list(indicators.items())[:2])
            table.add_row(item["code"], item.get("name", ""), item.get("pattern", ""), indicator_str, key=item["code"])
        if results:
            table.move_cursor(row=0)
            self._show_detail(0)
        else:
            self.query_one(DetailPanel).clear()
            self.query_one(DetailPanel).set_loading("未发现匹配股票")

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
        pass
