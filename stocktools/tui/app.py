from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.events import Key
from textual.theme import Theme
from textual.widgets import Static

from stocktools.data.repos.ai_logs_repo import AiLogsRepo
from stocktools.data.repos.kline_repo import KlineRepo
from stocktools.infra.paths import Paths
from stocktools.services.find_service import FindService
from stocktools.services.hold_service import HoldService
from stocktools.services.record_service import RecordService
from stocktools.tui.screens.holdings import HoldingsTab, HistoryModal
from stocktools.tui.screens.scan import ScanTab
from stocktools.tui.screens.watchlist import WatchlistTab
from stocktools.tui.widgets.input_modal import InputModal


TAB_NAMES = ["关注池", "持仓", "扫描"]


def _validate_price(value: str) -> str | None:
    try:
        p = float(value)
        if p <= 0:
            return "价格必须大于 0"
    except ValueError:
        return "请输入有效数字"
    return None


_ST_THEME = Theme(
    name="stocktools",
    primary="#89b4fa",
    secondary="#a6e3a1",
    accent="#fab387",
    warning="#f9e2af",
    error="#f38ba8",
    success="#a6e3a1",
    background="transparent",
    surface="transparent",
    panel="transparent",
    boost="transparent",
    dark=True,
    ansi=True,
    variables={
        "border": "white",
        "border-blurred": "white",
        "block-cursor-foreground": "ansi_black",
        "block-cursor-background": "transparent",
        "input-cursor-background": "transparent",
        "input-cursor-foreground": "ansi_bright_white",
        "input-cursor-text-style": "none",
        "input-selection-background": "transparent",
        "input-selection-foreground": "ansi_black",
        "screen-selection-background": "transparent",
        "screen-selection-foreground": "ansi_black",
    },
)


class StockToolsApp(App):

    CSS_PATH = "styles/app.tcss"
    theme = "stocktools"

    BINDINGS = [
        Binding("q", "quit", "退出", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.register_theme(_ST_THEME)
        paths = Paths.resolve()
        paths.init_databases()
        db = paths.database_path
        self._db = db
        self._record_svc = RecordService(db)
        self._hold_svc = HoldService(db)
        self._find_svc = FindService(db)
        self._kline_repo = KlineRepo(db)
        self._watch_svc = None
        self._alert_svc = None
        self._ai_logs_repo = AiLogsRepo(db)
        self._current_tab = 0

    def _get_watch_svc(self):
        if self._watch_svc is None:
            from stocktools.services.watch_service import WatchService
            self._watch_svc = WatchService(self._db)
        return self._watch_svc

    def _get_alert_svc(self):
        if self._alert_svc is None:
            from stocktools.services.alert_service import AlertService
            self._alert_svc = AlertService(self._db)
        return self._alert_svc

    def compose(self) -> ComposeResult:
        yield Static("", id="hint-bar")
        yield Static("", id="tab-bar")
        yield WatchlistTab()
        yield HoldingsTab()
        yield ScanTab()
        yield Static("", id="status-bar")

    def on_mount(self) -> None:
        self._tabs = [
            self.query_one(WatchlistTab),
            self.query_one(HoldingsTab),
            self.query_one(ScanTab),
        ]
        self._switch_tab(0)

    def _switch_tab(self, idx: int) -> None:
        self._current_tab = idx
        for i, tab in enumerate(self._tabs):
            tab.display = i == idx
        tab_parts = []
        for i, name in enumerate(TAB_NAMES):
            if i == idx:
                tab_parts.append(f"[bold bright_blue] {name} [/]")
            else:
                tab_parts.append(f"[dim] {name} [/]")
        self.query_one("#tab-bar", Static).update("  ".join(tab_parts))
        self.query_one("#hint-bar", Static).update(
            "[bright_blue]Tab[/][dim]:切换页面  "
            "[bright_blue]↑↓[/][dim]:选择  "
            "[bright_blue]q[/][dim]:退出[/]"
        )
        self._tabs[idx].refresh_data()
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        watchlist_count = len(self._record_svc.list_all())
        holdings_count = len(self._hold_svc.list_open())
        self.query_one("#status-bar", Static).update(
            f"[dim]关注: {watchlist_count} | 持仓: {holdings_count}[/]"
        )

    def _current_widget(self):
        return self._tabs[self._current_tab]

    def on_key(self, event: Key) -> None:
        if event.key == "tab":
            self._switch_tab((self._current_tab + 1) % len(self._tabs))
            event.prevent_default()
            event.stop()
            return
        if event.key == "shift+tab":
            self._switch_tab((self._current_tab - 1) % len(self._tabs))
            event.prevent_default()
            event.stop()
            return

        handler = self._get_handler(event.key)
        if handler:
            handler()
            event.prevent_default()
            event.stop()

    def _get_handler(self, key: str):
        tab = self._current_tab
        if tab == 0:
            return {
                "a": self._wl_add,
                "d": self._wl_remove,
                "g": self._wl_go,
                "n": self._wl_note,
                "w": self._wl_watch,
                "enter": self._wl_enter,
            }.get(key)
        elif tab == 1:
            return {
                "s": self._hd_stop,
                "t": self._hd_target,
                "n": self._hd_note,
                "x": self._hd_close,
                "r": self._hd_reduce,
                "upper_a": self._hd_alert,
                "A": self._hd_alert,
                "shift+upper_a": self._hd_alert_all,
                "shift+a": self._hd_alert_all,
                "h": self._hd_history,
            }.get(key)
        elif tab == 2:
            return {
                "enter": self._sc_add,
                "space": self._sc_run,
                "c": self._sc_export,
                "left": self._sc_prev_scanner,
                "right": self._sc_next_scanner,
            }.get(key)
        return None

    # ── Watchlist ─────────────────────────────────────────

    def _wl_add(self) -> None:
        self.push_screen(
            InputModal("添加股票到关注池", "输入股票代码"),
            self._on_add_stock,
        )

    def _on_add_stock(self, code: str | None) -> None:
        if code:
            try:
                self._record_svc.add(code)
                self._current_widget().refresh_data()
                self._update_status_bar()
            except ValueError as e:
                self.notify(str(e), severity="error")

    def _wl_remove(self) -> None:
        item = self._current_widget().selected_item()
        if item:
            self._record_svc.remove(item["code"])
            self._current_widget().refresh_data()
            self._update_status_bar()

    def _wl_go(self) -> None:
        item = self._current_widget().selected_item()
        if item:
            self._record_svc.go(item["code"])
            self._current_widget().refresh_data()

    def _wl_note(self) -> None:
        item = self._current_widget().selected_item()
        if not item:
            return
        self.push_screen(
            InputModal(f"编辑备注 - {item['code']}", "输入备注内容"),
            self._on_watchlist_note,
        )

    def _on_watchlist_note(self, note: str | None) -> None:
        if note:
            item = self._current_widget().selected_item()
            if item:
                self._record_svc.note(item["code"], note, replace=True)
                self._current_widget().refresh_data()

    def _wl_watch(self) -> None:
        item = self._current_widget().selected_item()
        if not item:
            return
        detail = self._current_widget().query_one("DetailPanel")
        detail.set_loading("买入分析中...")
        self.run_worker(self._do_watch(item["code"]), exclusive=True)

    async def _do_watch(self, code: str) -> None:
        try:
            await asyncio.to_thread(self._get_watch_svc().analyze, code)
        except Exception as e:
            self.notify(str(e), severity="error")
        self._current_widget().refresh_data()

    def _wl_enter(self) -> None:
        item = self._current_widget().selected_item()
        if not item:
            return
        self.push_screen(
            InputModal(f"转入持仓 - {item['code']}", "输入买入价", _validate_price),
            self._on_hold_in,
        )

    def _on_hold_in(self, price_str: str | None) -> None:
        if not price_str:
            return
        item = self._current_widget().selected_item()
        if item:
            self._hold_svc.add_entry(item["code"], float(price_str))
            self._record_svc.remove(item["code"])
            self._current_widget().refresh_data()
            self._update_status_bar()

    # ── Holdings ──────────────────────────────────────────

    def _hd_stop(self) -> None:
        item = self._current_widget().selected_item()
        if not item:
            return
        self.push_screen(
            InputModal(f"设置止损价 - {item['code']}", "输入止损价", _validate_price),
            self._on_set_stop,
        )

    def _on_set_stop(self, price_str: str | None) -> None:
        if price_str:
            item = self._current_widget().selected_item()
            if item:
                self._hold_svc.set_fields(item["code"], stop=float(price_str))
                self._current_widget().refresh_data()

    def _hd_target(self) -> None:
        item = self._current_widget().selected_item()
        if not item:
            return
        self.push_screen(
            InputModal(f"设置目标价 - {item['code']}", "输入目标价", _validate_price),
            self._on_set_target,
        )

    def _on_set_target(self, price_str: str | None) -> None:
        if price_str:
            item = self._current_widget().selected_item()
            if item:
                self._hold_svc.set_fields(item["code"], target=float(price_str))
                self._current_widget().refresh_data()

    def _hd_note(self) -> None:
        item = self._current_widget().selected_item()
        if not item:
            return
        self.push_screen(
            InputModal(f"编辑备注 - {item['code']}", "输入备注内容"),
            self._on_holding_note,
        )

    def _on_holding_note(self, note: str | None) -> None:
        if note:
            item = self._current_widget().selected_item()
            if item:
                self._hold_svc.set_fields(item["code"], note=note)
                self._current_widget().refresh_data()

    def _hd_close(self) -> None:
        item = self._current_widget().selected_item()
        if not item:
            return
        self.push_screen(
            InputModal(f"平仓 - {item['code']}", "输入卖出价", _validate_price),
            self._on_close_position,
        )

    def _on_close_position(self, price_str: str | None) -> None:
        if price_str:
            item = self._current_widget().selected_item()
            if item:
                self._hold_svc.exit(item["code"], float(price_str))
                self._current_widget().refresh_data()
                self._update_status_bar()

    def _hd_reduce(self) -> None:
        item = self._current_widget().selected_item()
        if not item:
            return
        self.push_screen(
            InputModal(f"减仓 - {item['code']}", "输入卖出价", _validate_price),
            self._on_reduce_position,
        )

    def _on_reduce_position(self, price_str: str | None) -> None:
        if price_str:
            item = self._current_widget().selected_item()
            if item:
                self._hold_svc.exit(item["code"], float(price_str), decrease=True)
                self._current_widget().refresh_data()

    def _hd_alert(self) -> None:
        item = self._current_widget().selected_item()
        if not item:
            return
        detail = self._current_widget().query_one("DetailPanel")
        detail.set_loading("卖出分析中...")
        self.run_worker(self._do_alert(item["code"]), exclusive=True)

    async def _do_alert(self, code: str) -> None:
        try:
            await asyncio.to_thread(self._get_alert_svc().analyze, code)
        except Exception as e:
            self.notify(str(e), severity="error")
        self._current_widget().refresh_data()

    def _hd_alert_all(self) -> None:
        detail = self._current_widget().query_one("DetailPanel")
        detail.set_loading("全部持仓分析中...")
        self.run_worker(self._do_alert_all(), exclusive=True)

    async def _do_alert_all(self) -> None:
        try:
            await asyncio.to_thread(self._get_alert_svc().analyze)
        except Exception as e:
            self.notify(str(e), severity="error")
        self._current_widget().refresh_data()

    def _hd_history(self) -> None:
        records = self._hold_svc.history(near=50)
        self.push_screen(HistoryModal(records))

    # ── Scan ──────────────────────────────────────────────

    def _sc_add(self) -> None:
        item = self._current_widget().selected_item()
        if item:
            try:
                self._record_svc.add(item["code"])
                self.notify(f"{item['code']} 已加入关注池")
                self._update_status_bar()
            except ValueError as e:
                self.notify(str(e), severity="error")

    def _sc_prev_scanner(self) -> None:
        self._current_widget().select_prev_scanner()

    def _sc_next_scanner(self) -> None:
        self._current_widget().select_next_scanner()

    def _sc_run(self) -> None:
        self._current_widget().run_scan()

    def _sc_export(self) -> None:
        self.push_screen(
            InputModal("导出 CSV", "输入文件路径"),
            self._on_export_csv,
        )

    def _on_export_csv(self, path_str: str | None) -> None:
        if not path_str:
            return
        widget = self._current_widget()
        if not widget._results:
            self.notify("没有扫描结果可导出", severity="warning")
            return
        try:
            from stocktools.output.csv_writer import write_csv
            write_csv(widget._results, path_str)
            self.notify(f"已导出到 {path_str}")
        except Exception as e:
            self.notify(str(e), severity="error")


def run_tui() -> None:
    app = StockToolsApp()
    app.run()
