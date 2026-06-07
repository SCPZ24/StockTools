from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseScanner
from .results import ScanResult
from .utils import max_drawdown, normalize_df


DEFAULTS = {
    "min_days": 60,
    "excess_return_min": 0.20,
    "drawdown_max": 0.18,
    "r_squared_min": 0.72,
    "up_fraction_min": 0.55,
    "vol_expand_max": 1.6,
    "baseline_return": 0.0,
}


def _trend_r2(closes: np.ndarray) -> float:
    """R² of log-price vs time — how steadily (not how fast) the stock climbs."""
    y = np.log(closes)
    x = np.arange(len(y), dtype=float)
    n = len(x)
    denom = n * (x * x).sum() - x.sum() ** 2
    if abs(denom) < 1e-10:
        return 0.0
    slope = (n * (x * y).sum() - x.sum() * y.sum()) / denom
    intercept = (y.sum() - slope * x.sum()) / n
    pred = slope * x + intercept
    ss_res = ((y - pred) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    return float(1 - ss_res / ss_tot) if ss_tot > 1e-12 else 0.0


class IndependentScanner(BaseScanner):
    name = "independent"
    label = "独立行情"

    def detect(self, df: pd.DataFrame, **kwargs) -> ScanResult:
        p = {**DEFAULTS, **kwargs}
        data = normalize_df(df)
        min_days = int(p["min_days"])
        if len(data) < min_days + 60:
            return ScanResult(False, self.name)

        recent = data.tail(min_days)
        closes = recent["close"].values
        volumes = recent["volume"].values

        start_price = float(closes[0])
        latest_price = float(closes[-1])
        if start_price <= 0 or float(np.min(closes)) <= 0:
            return ScanResult(False, self.name)

        # Relative strength: must clearly beat the broad market over the window.
        total_return = latest_price / start_price - 1
        excess = total_return - float(p["baseline_return"])
        if excess < float(p["excess_return_min"]):
            return ScanResult(False, self.name)

        # Steady, low-drawdown advance — "独立" means it grinds up on its own,
        # not a single spike that round-trips.
        dd = max_drawdown(closes)
        if dd > float(p["drawdown_max"]):
            return ScanResult(False, self.name)

        r2 = _trend_r2(closes)
        if r2 < float(p["r_squared_min"]):
            return ScanResult(False, self.name)

        diffs = np.diff(closes)
        up_fraction = float(np.mean(diffs > 0)) if len(diffs) else 0.0
        if up_fraction < float(p["up_fraction_min"]):
            return ScanResult(False, self.name)

        # No volume climax (which would signal distribution rather than a trend).
        recent_vol = float(np.mean(volumes[-20:]))
        prior_vol = float(np.mean(volumes[:-20]))
        if prior_vol <= 0:
            return ScanResult(False, self.name)
        vol_ratio = recent_vol / prior_vol
        if vol_ratio > float(p["vol_expand_max"]):
            return ScanResult(False, self.name)

        score = excess * 100 - dd * 40 + r2 * 60 + up_fraction * 40

        indicators = {
            "price": round(latest_price, 2),
            "return_60d_pct": round(total_return * 100, 1),
            "excess_return_pct": round(excess * 100, 1),
            "max_drawdown_pct": round(dd * 100, 1),
            "trend_r2": round(r2, 3),
            "up_fraction_pct": round(up_fraction * 100, 1),
            "vol_ratio": round(vol_ratio, 2),
            "score": round(score, 1),
        }
        return ScanResult(True, self.name, indicators)
