from __future__ import annotations

from textual.app import ComposeResult
from textual.events import Resize
from textual.widget import Widget

from stocktools.tui.widgets.detail_panel import DetailPanel
from stocktools.tui.widgets.kline_chart import KlineChart


WIDE_CHART_MIN_WIDTH = 160
WIDE_CHART_MIN_HEIGHT = 24


class StockInspector(Widget):
    """Right-side stock detail and optional wide-screen K-line chart."""

    def compose(self) -> ComposeResult:
        yield DetailPanel()
        yield KlineChart(id="kline-chart")

    def on_mount(self) -> None:
        self.sync_chart_visibility()

    def on_resize(self, event: Resize) -> None:
        del event
        self.sync_chart_visibility()

    def sync_chart_visibility(self) -> None:
        chart = self.query_one(KlineChart)
        size = self.app.size
        visible = size.width >= WIDE_CHART_MIN_WIDTH and size.height >= WIDE_CHART_MIN_HEIGHT
        chart.display = visible
        self.set_class(visible, "chart-visible")
        self.set_class(not visible, "chart-hidden")

    def show_chart_for(self, code: str, name: str) -> None:
        self.sync_chart_visibility()
        chart = self.query_one(KlineChart)
        try:
            df = self.app._kline_repo.get_kline_rows(code)
        except Exception:
            chart.set_error(code, "读取 K 线失败")
            return
        chart.set_klines(code, name, df)

    def clear_all(self) -> None:
        self.query_one(DetailPanel).clear()
        self.query_one(KlineChart).clear()
