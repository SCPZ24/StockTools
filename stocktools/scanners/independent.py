from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseScanner
from .results import ScanResult
from .utils import max_drawdown, normalize_df


DEFAULTS = {
    "min_days": 60,
    "excess_return_min": 0.15,
    "drawdown_max": 0.25,
    "vol_shrink_max": 0.80,
    "segment_positive": True,
    "baseline_return": 0.0,
}


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
        if start_price <= 0:
            return ScanResult(False, self.name)

        total_return = latest_price / start_price - 1
        excess = total_return - float(p["baseline_return"])
        if excess < float(p["excess_return_min"]):
            return ScanResult(False, self.name)

        dd = max_drawdown(closes)
        if dd > float(p["drawdown_max"]):
            return ScanResult(False, self.name)

        seg_len = min_days // 3
        if p["segment_positive"]:
            for i in range(3):
                seg = closes[i * seg_len : (i + 1) * seg_len]
                if float(seg[-1]) <= float(seg[0]):
                    return ScanResult(False, self.name)

        recent_vol = float(np.mean(volumes[-20:]))
        prior_vol = float(np.mean(volumes[:-20]))
        if prior_vol <= 0:
            return ScanResult(False, self.name)
        vol_ratio = recent_vol / prior_vol
        if vol_ratio > float(p["vol_shrink_max"]):
            return ScanResult(False, self.name)

        score = excess * 100 - dd * 30 + (1 - vol_ratio) * 50

        indicators = {
            "price": round(latest_price, 2),
            "return_60d_pct": round(total_return * 100, 1),
            "excess_return_pct": round(excess * 100, 1),
            "max_drawdown_pct": round(dd * 100, 1),
            "vol_shrink_ratio": round(vol_ratio, 2),
            "score": round(score, 1),
        }
        return ScanResult(True, self.name, indicators)

