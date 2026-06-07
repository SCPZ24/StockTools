from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if not is_datetime64_any_dtype(out["date"]):
        out["date"] = pd.to_datetime(out["date"])
    for col in ("open", "close", "high", "low", "volume"):
        if not is_numeric_dtype(out[col]):
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["date", "open", "close", "high", "low", "volume"]).sort_values("date").reset_index(drop=True)


def weekly_df(df: pd.DataFrame) -> pd.DataFrame:
    daily = normalize_df(df)
    if daily.empty:
        return daily
    dates = daily["date"]
    week_offsets = (4 - dates.dt.weekday.to_numpy()) % 7
    week_ends = (dates + pd.to_timedelta(week_offsets, unit="D")).dt.normalize().to_numpy()
    is_start = np.empty(len(week_ends), dtype=bool)
    is_start[0] = True
    is_start[1:] = week_ends[1:] != week_ends[:-1]
    starts = np.flatnonzero(is_start)
    ends = np.r_[starts[1:], len(daily)]

    opens = daily["open"].to_numpy()
    highs = daily["high"].to_numpy()
    lows = daily["low"].to_numpy()
    closes = daily["close"].to_numpy()
    volumes = daily["volume"].to_numpy()

    return pd.DataFrame(
        {
            "date": week_ends[starts],
            "open": opens[starts],
            "high": np.maximum.reduceat(highs, starts),
            "low": np.minimum.reduceat(lows, starts),
            "close": closes[ends - 1],
            "volume": np.add.reduceat(volumes, starts),
        }
    )


def max_drawdown(values) -> float:
    peak = None
    worst = 0.0
    for value in values:
        value = float(value)
        peak = value if peak is None else max(peak, value)
        if peak > 0:
            worst = min(worst, (value - peak) / peak)
    return abs(worst)
