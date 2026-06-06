from __future__ import annotations

import pandas as pd


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    for col in ("open", "close", "high", "low", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["date", "open", "close", "high", "low", "volume"]).sort_values("date").reset_index(drop=True)


def weekly_df(df: pd.DataFrame) -> pd.DataFrame:
    daily = normalize_df(df)
    if daily.empty:
        return daily
    indexed = daily.set_index("date")
    weekly = indexed.resample("W-FRI").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    weekly = weekly.dropna().reset_index()
    return weekly


def max_drawdown(values) -> float:
    peak = None
    worst = 0.0
    for value in values:
        value = float(value)
        peak = value if peak is None else max(peak, value)
        if peak > 0:
            worst = min(worst, (value - peak) / peak)
    return abs(worst)

