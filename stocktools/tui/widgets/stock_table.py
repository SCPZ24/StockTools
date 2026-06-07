from __future__ import annotations

from textual.widgets import DataTable

from stocktools.tui.stock_style import stock_name_cell


class StockDataTable(DataTable):
    """DataTable with one shared stock-name rendering path."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("cursor_foreground_priority", "renderable")
        super().__init__(*args, **kwargs)

    def stock_name_cell(self, code: str, name: str):
        return stock_name_cell(self.app._kline_repo, code, name)

    def add_stock_row(self, code: str, name: str, *cells, key: str | None = None) -> None:
        self.add_row(self.stock_name_cell(code, name), *cells, key=key or code)
