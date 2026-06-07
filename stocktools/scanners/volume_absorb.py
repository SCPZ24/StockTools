from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseScanner
from .results import ScanResult
from .utils import normalize_df


DEFAULTS = {
    "lookback": 5,
    "baseline_days": 60,
    "vol_spike_min": 3.0,
    "strong_single_ratio": 4.0,
    "min_spike_days": 1,
    "gain_min": 0.01,
    "max_gain": 0.12,
    "position_window": 120,
    "position_max": 0.40,
    "held_tolerance": 0.03,
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

        max_vol_ratio = float(spike_days["volume"].max() / baseline_avg)
        # A lone, merely-2x up-day is noise. Demand either several spike days or
        # one genuinely explosive bar.
        if len(spike_days) < 2 and max_vol_ratio < p["strong_single_ratio"]:
            return ScanResult(False, self.name)

        # 吸筹 happens at a low. Require price in the lower part of its range.
        window = data.tail(min(p["position_window"], len(data)))
        rng_low = float(window["low"].min())
        rng_high = float(window["high"].max())
        latest_close = float(data.iloc[-1]["close"])
        if rng_high <= rng_low:
            return ScanResult(False, self.name)
        range_pos = (latest_close - rng_low) / (rng_high - rng_low)
        if range_pos > p["position_max"]:
            return ScanResult(False, self.name)

        first_spike_idx = spike_days.index[0]
        pos_in_data = data.index.get_loc(first_spike_idx)
        price_before = float(data.iloc[pos_in_data - 1]["close"]) if pos_in_data > 0 else float(spike_days.iloc[0]["open"])
        gain = (latest_close - price_before) / price_before if price_before > 0 else 0

        # Absorption = heavy volume but price stays contained (not a chase),
        # and the buying level holds (price hasn't been distributed back down).
        if gain < p["gain_min"] or gain > p["max_gain"]:
            return ScanResult(False, self.name)
        spike_close_avg = float(spike_days["close"].mean())
        if latest_close < spike_close_avg * (1 - p["held_tolerance"]):
            return ScanResult(False, self.name)

        avg_spike_ratio = float(spike_days["volume"].mean() / baseline_avg)

        score = avg_spike_ratio * 20 + len(spike_days) * 15 + gain * 80 + (1 - range_pos) * 60

        indicators = {
            "price": round(latest_close, 2),
            "gain_pct": round(gain * 100, 1),
            "spike_days": int(len(spike_days)),
            "max_vol_ratio": round(max_vol_ratio, 2),
            "avg_spike_ratio": round(avg_spike_ratio, 2),
            "range_pos_pct": round(range_pos * 100, 1),
            "score": round(score, 1),
        }
        return ScanResult(True, self.name, indicators)
