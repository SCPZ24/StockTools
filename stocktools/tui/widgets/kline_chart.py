from __future__ import annotations

import math
from typing import Any

from rich.text import Text
from textual.events import Resize
from textual.widgets import Static


UP_COLOR = "#e60012"
DOWN_COLOR = "#009900"
FLAT_COLOR = "white"
DIM_STYLE = "dim"

LABEL_WIDTH = 8
MIN_CHART_WIDTH = 48
MIN_CHART_HEIGHT = 14


def _format_price(value: float) -> str:
    return f"{value:.2f}"


def _format_volume(value: float) -> str:
    if value >= 100_000_000:
        return f"{value / 100_000_000:.1f}亿手"
    if value >= 10_000:
        return f"{value / 10_000:.1f}万手"
    return f"{value:.0f}手"


def _day_style(open_price: float, close_price: float) -> str:
    if close_price > open_price:
        return UP_COLOR
    if close_price < open_price:
        return DOWN_COLOR
    return FLAT_COLOR


def _rows_from_source(data: Any) -> list[dict]:
    required = ["date", "open", "close", "high", "low", "volume"]

    if data is None:
        return []
    if getattr(data, "empty", False):
        return []
    if hasattr(data, "columns") and any(col not in data.columns for col in required):
        return []
    if hasattr(data, "loc") and hasattr(data, "to_dict"):
        source_rows = data.loc[:, required].to_dict("records")
    else:
        source_rows = list(data)

    rows: list[dict] = []
    for row in source_rows:
        try:
            prepared = {
                "date": str(row["date"]),
                "open": float(row["open"]),
                "close": float(row["close"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "volume": float(row["volume"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(prepared[col]) for col in ("open", "close", "high", "low", "volume")):
            continue
        rows.append(prepared)
    rows.sort(key=lambda item: item["date"])
    return rows


def _prepare_visible_klines(data: Any, width: int) -> list[dict]:
    rows = _rows_from_source(data)
    if not rows:
        return []
    plot_width = max(1, width - LABEL_WIDTH - 1)
    return rows[-min(len(rows), plot_width):]


def _price_to_row(price: float, lower: float, upper: float, rows: int) -> int:
    if rows <= 1 or upper <= lower:
        return 0
    ratio = (upper - price) / (upper - lower)
    return max(0, min(rows - 1, round(ratio * (rows - 1))))


def _append_line(text: Text, segments: list[tuple[str, str | None]], width: int) -> None:
    used = 0
    for content, style in segments:
        text.append(content, style=style)
        used += len(content)
    if used < width:
        text.append(" " * (width - used))


def _line_from_cells(label: str, cells: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
    return [(label[-LABEL_WIDTH:].rjust(LABEL_WIDTH), DIM_STYLE), (" ", None), *cells]


def _plain_line(content: str, width: int, style: str | None = None) -> list[tuple[str, str | None]]:
    if len(content) > width:
        content = content[:width]
    return [(content, style)]


def build_kline_chart_text(code: str, name: str, df: Any, width: int, height: int) -> Text:
    """Build a transparent Rich Text candlestick chart with volume."""
    if width < MIN_CHART_WIDTH or height < MIN_CHART_HEIGHT:
        return Text("尺寸不足，无法显示 K 线图", style=DIM_STYLE, no_wrap=True)

    visible = _prepare_visible_klines(df, width)
    if not visible:
        return Text("暂无 K 线数据", style=DIM_STYLE, no_wrap=True)

    plot_width = len(visible)

    header_rows = 1
    footer_rows = 2
    gap_rows = 1
    plot_rows = max(1, height - header_rows - footer_rows - gap_rows)
    volume_rows = max(3, min(6, plot_rows // 4))
    price_rows = max(1, plot_rows - volume_rows)

    price_values: list[float] = []
    for row in visible:
        price_values.append(row["high"])
        price_values.append(row["low"])
    lower = min(price_values)
    upper = max(price_values)
    span = upper - lower
    padding = span * 0.03 if span else max(abs(upper) * 0.03, 1.0)
    lower -= padding
    upper += padding

    price_cells: list[list[tuple[str, str | None]]] = [
        [(" ", None) for _ in range(plot_width)] for _ in range(price_rows)
    ]
    for x, row in enumerate(visible):
        open_price = row["open"]
        close_price = row["close"]
        high_price = row["high"]
        low_price = row["low"]
        style = _day_style(open_price, close_price)
        high_y = _price_to_row(high_price, lower, upper, price_rows)
        low_y = _price_to_row(low_price, lower, upper, price_rows)
        open_y = _price_to_row(open_price, lower, upper, price_rows)
        close_y = _price_to_row(close_price, lower, upper, price_rows)
        for y in range(min(high_y, low_y), max(high_y, low_y) + 1):
            price_cells[y][x] = ("│", style)
        for y in range(min(open_y, close_y), max(open_y, close_y) + 1):
            price_cells[y][x] = ("█", style)

    max_volume = max(row["volume"] for row in visible) if visible else 0.0
    volume_cells: list[list[tuple[str, str | None]]] = [
        [(" ", None) for _ in range(plot_width)] for _ in range(volume_rows)
    ]
    if max_volume > 0:
        for x, row in enumerate(visible):
            volume = row["volume"]
            bar_height = max(1, round((volume / max_volume) * volume_rows)) if volume > 0 else 0
            style = _day_style(row["open"], row["close"])
            for y in range(volume_rows - bar_height, volume_rows):
                volume_cells[y][x] = ("█", style)

    latest = visible[-1]
    latest_close = latest["close"]
    pct_text = "--"
    pct_style = FLAT_COLOR
    prepared = _rows_from_source(df)
    if len(prepared) >= 2:
        previous_close = prepared[-2]["close"]
        if previous_close:
            pct = (latest_close - previous_close) / previous_close * 100
            pct_text = f"{pct:+.2f}%"
            pct_style = UP_COLOR if pct > 0 else DOWN_COLOR if pct < 0 else FLAT_COLOR

    lines: list[list[tuple[str, str | None]]] = []
    title = f"{code} {name}  收 {_format_price(latest_close)}  "
    lines.append([(title, "bold"), (pct_text, pct_style)])

    mid_row = price_rows // 2
    for y, cells in enumerate(price_cells):
        if y == 0:
            label = _format_price(upper)
        elif y == mid_row:
            label = _format_price((upper + lower) / 2)
        elif y == price_rows - 1:
            label = _format_price(lower)
        else:
            label = ""
        lines.append(_line_from_cells(label, cells))

    lines.append(_plain_line("", width))

    for y, cells in enumerate(volume_cells):
        label = _format_volume(max_volume) if y == 0 and max_volume > 0 else ""
        lines.append(_line_from_cells(label, cells))

    start_date = str(visible[0]["date"])[:10]
    end_date = str(visible[-1]["date"])[:10]
    lines.append(_plain_line(f"{start_date} - {end_date}  成交量Max {_format_volume(max_volume)}", width, DIM_STYLE))
    lines.append(_plain_line("日K  成交量", width, DIM_STYLE))

    lines = lines[:height]
    text = Text(no_wrap=True)
    for i, line in enumerate(lines):
        _append_line(text, line, width)
        if i != len(lines) - 1:
            text.append("\n")
    return text


class KlineChart(Static):
    """Transparent self-rendered daily K-line chart."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("markup", False)
        super().__init__("", *args, **kwargs)
        self._code: str | None = None
        self._name: str = ""
        self._klines: Any = []

    @property
    def selected_code(self) -> str | None:
        return self._code

    def set_klines(self, code: str, name: str, df: Any) -> None:
        self._code = code
        self._name = name
        self._klines = df.copy() if hasattr(df, "copy") else list(df)
        self._refresh_chart()

    def set_error(self, code: str, message: str) -> None:
        self._code = code
        self._name = ""
        self._klines = []
        self.update(Text(message, style=DIM_STYLE, no_wrap=True), layout=False)

    def clear(self) -> None:
        self._code = None
        self._name = ""
        self._klines = []
        self.update("", layout=False)

    def on_resize(self, event: Resize) -> None:
        del event
        if self._code:
            self._refresh_chart()

    def _refresh_chart(self) -> None:
        if not self._code:
            self.update("", layout=False)
            return
        self.update(
            build_kline_chart_text(self._code, self._name, self._klines, self.size.width, self.size.height),
            layout=False,
        )
