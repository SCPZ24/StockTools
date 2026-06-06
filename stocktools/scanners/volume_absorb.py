from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseScanner
from .results import ScanResult
from .utils import normalize_df


class VolumeAbsorbScanner(BaseScanner):
    name = "volume_absorb"
    label = "爆量吸筹"

    def detect(self, df: pd.DataFrame, **kwargs) -> ScanResult:
        vol_ratio_min = float(kwargs.get("vol_ratio_min", 1.8))
        range_max = float(kwargs.get("range_max", 0.25))
        support_lift_min = float(kwargs.get("support_lift_min", 0.08))
        data = normalize_df(df)
        if len(data) < 80:
            return ScanResult(False, self.name)
        recent = data.tail(20)
        prev = data.iloc[-80:-20]
        recent_avg = float(recent["volume"].mean())
        prev_avg = float(prev["volume"].mean())
        if prev_avg <= 0:
            return ScanResult(False, self.name)
        vol_ratio = recent_avg / prev_avg
        high = float(recent["high"].max())
        low = float(recent["low"].min())
        price_range = (high - low) / low if low > 0 else 999
        support_low = float(data.tail(60)["low"].min())
        latest = float(data.iloc[-1]["close"])
        support_lift = (latest - support_low) / support_low if support_low > 0 else 0
        up_vol = recent.loc[recent["close"] >= recent["open"], "volume"]
        down_vol = recent.loc[recent["close"] < recent["open"], "volume"]
        up_down_ratio = float(up_vol.mean() / down_vol.mean()) if len(up_vol) and len(down_vol) else 1.0
        matched = vol_ratio >= vol_ratio_min and price_range <= range_max and support_lift >= support_lift_min and up_down_ratio >= 1.0
        indicators = {
            "price": round(latest, 2),
            "vol_ratio": round(vol_ratio, 2),
            "range_pct": round(price_range * 100, 1),
            "support_lift_pct": round(support_lift * 100, 1),
            "up_down_vol_ratio": round(up_down_ratio, 2),
            "score": round(vol_ratio * 20 + max(0, range_max - price_range) * 100 + support_lift * 50, 1),
        }
        return ScanResult(matched, self.name, indicators if matched else {})

