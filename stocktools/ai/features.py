from __future__ import annotations

import math

import pandas as pd

from stocktools.scanners.utils import normalize_df


def compute_features(klines: pd.DataFrame) -> dict:
    data = normalize_df(klines)
    if data.empty:
        return {"bars": 0, "recent_ohlcv": []}
    close = data["close"]
    latest = data.iloc[-1]
    features: dict[str, object] = {
        "bars": len(data),
        "date": str(latest["date"].date() if hasattr(latest["date"], "date") else latest["date"]),
        "close": _round(latest["close"]),
        "pct_chg": _round(_ret(close.iloc[-2], close.iloc[-1]) if len(close) >= 2 else 0.0),
        "recent_ohlcv": [
            {
                "date": str(row["date"].date() if hasattr(row["date"], "date") else row["date"]),
                "open": _round(row["open"]),
                "high": _round(row["high"]),
                "low": _round(row["low"]),
                "close": _round(row["close"]),
                "volume": _round(row["volume"]),
            }
            for _, row in data.tail(5).iterrows()
        ],
    }
    for period in (5, 10, 20, 60):
        ma = close.rolling(period).mean()
        features[f"ma{period}"] = _round(ma.iloc[-1]) if not math.isnan(float(ma.iloc[-1])) else None
    for period in (5, 10, 20):
        features[f"ma{period}_slope"] = _ma_slope(close, period)
    for period in (20, 60):
        ma_value = features.get(f"ma{period}")
        features[f"dist_to_ma{period}"] = _round(_ret(ma_value, latest["close"])) if ma_value else None
    for days in (5, 10, 20):
        features[f"ret_{days}d"] = _round(_window_ret(close, days))
    returns = close.pct_change().tail(20).dropna()
    features["volatility_20d"] = _round(float(returns.std()) * 100) if not returns.empty else 0.0
    return features


def _window_ret(close: pd.Series, days: int) -> float:
    if len(close) < days + 1:
        return 0.0
    return _ret(close.iloc[-days - 1], close.iloc[-1])


def _ma_slope(close: pd.Series, period: int) -> float | None:
    ma = close.rolling(period).mean()
    if len(ma) < period + 5:
        return None
    prev = ma.iloc[-6]
    curr = ma.iloc[-1]
    if pd.isna(prev) or pd.isna(curr) or float(prev) <= 0:
        return None
    return _round((float(curr) - float(prev)) / float(prev) * 100 / 5)


def _ret(start, end) -> float:
    start_f = float(start)
    return (float(end) - start_f) / start_f * 100 if start_f > 0 else 0.0


def _round(value) -> float:
    return round(float(value), 4)
