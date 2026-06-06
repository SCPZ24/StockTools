from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseScanner
from .results import ScanResult
from .utils import normalize_df


DEFAULTS = {
    "lookback": 5,
    "baseline_days": 60,
    "vol_spike_min": 2.0,
    "min_spike_days": 1,
    "max_gain": 0.20,
}


class VolumeAbsorbScanner(BaseScanner):
    name = "volume_absorb"
    label = "爆量吸筹"

    def detect(self, df: pd.DataFrame, **kwargs) -> ScanResult:
        p = {**DEFAULTS, **kwargs}
        data = normalize_df(df)
        required = p["baseline_days"] + p["lookback"]
        if len(data) < required:
            return ScanResult(False, self.name)

        recent = data.tail(p["lookback"])
        baseline = data.iloc[-(p["baseline_days"] + p["lookback"]):-p["lookback"]]
        baseline_avg = float(baseline["volume"].mean())
        if baseline_avg <= 0:
            return ScanResult(False, self.name)

        spike_days = recent[
            (recent["volume"] >= baseline_avg * p["vol_spike_min"])
            & (recent["close"] > recent["open"])
        ]

        if len(spike_days) < p["min_spike_days"]:
            return ScanResult(False, self.name)

        first_spike_idx = spike_days.index[0]
        pos_in_data = data.index.get_loc(first_spike_idx)
        price_before = float(data.iloc[pos_in_data - 1]["close"]) if pos_in_data > 0 else float(spike_days.iloc[0]["open"])
        latest_close = float(data.iloc[-1]["close"])
        gain = (latest_close - price_before) / price_before if price_before > 0 else 0

        if gain <= 0 or gain > p["max_gain"]:
            return ScanResult(False, self.name)

        max_vol_ratio = float(spike_days["volume"].max() / baseline_avg)
        avg_spike_ratio = float(spike_days["volume"].mean() / baseline_avg)

        score = avg_spike_ratio * 25 + len(spike_days) * 15 + gain * 100

        indicators = {
            "price": round(latest_close, 2),
            "gain_pct": round(gain * 100, 1),
            "spike_days": int(len(spike_days)),
            "max_vol_ratio": round(max_vol_ratio, 2),
            "avg_spike_ratio": round(avg_spike_ratio, 2),
            "score": round(score, 1),
        }
        return ScanResult(True, self.name, indicators)

