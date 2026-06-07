from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseScanner
from .results import ScanResult
from .utils import weekly_df


DEFAULTS = {
    "min_weeks": 12,
    "max_weeks": 52,
    "slope_min": 0.003,
    "slope_max": 0.03,
    "width_min": 0.08,
    "width_max": 0.35,
    "r_squared_min": 0.75,
    "r_squared_hi_min": 0.55,
    "parallelism": 0.30,
    "position_max": 0.55,
    "zigzag_pct": 0.05,
    "min_support": 3,
    "min_resistance": 3,
    "containment_min": 0.85,
    "tolerance": 0.03,
}


def _zigzag_pivots(highs: np.ndarray, lows: np.ndarray, pct: float):
    if len(highs) < 3:
        return [], []
    pivots = []
    last_val = lows[0]
    last_idx = 0
    last_dir = -1
    for i in range(1, len(highs)):
        if last_dir == -1:
            if highs[i] >= last_val * (1 + pct):
                pivots.append((last_idx, -1, last_val))
                last_val, last_idx, last_dir = highs[i], i, 1
            elif lows[i] < last_val:
                last_val, last_idx = lows[i], i
        else:
            if lows[i] <= last_val * (1 - pct):
                pivots.append((last_idx, 1, last_val))
                last_val, last_idx, last_dir = lows[i], i, -1
            elif highs[i] > last_val:
                last_val, last_idx = highs[i], i
    pivots.append((last_idx, last_dir, last_val))
    return [(i, v) for i, d, v in pivots if d == -1], [(i, v) for i, d, v in pivots if d == 1]


def _fit_line(points):
    if len(points) < 2:
        return None, None, 0.0
    x = np.array([p[0] for p in points], dtype=float)
    y = np.array([p[1] for p in points], dtype=float)
    n = len(x)
    denom = n * (x * x).sum() - x.sum() * x.sum()
    if abs(denom) < 1e-10:
        return None, None, 0.0
    slope = (n * (x * y).sum() - x.sum() * y.sum()) / denom
    intercept = (y.sum() - slope * x.sum()) / n
    pred = slope * x + intercept
    ss_res = ((y - pred) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot > 1e-10 else 0.0
    return slope, intercept, r2


class ChannelScanner(BaseScanner):
    name = "channel"
    label = "上升通道"

    def detect(self, df: pd.DataFrame, **kwargs) -> ScanResult:
        p = {**DEFAULTS, **kwargs}
        data = weekly_df(df)
        if len(data) < p["min_weeks"]:
            return ScanResult(False, self.name)
        closes = data["close"].values
        highs = data["high"].values
        lows = data["low"].values
        n = len(closes)
        best = None
        best_score = 0.0
        for length in range(min(p["max_weeks"], n), p["min_weeks"] - 1, -2):
            start = n - length
            minima, maxima = _zigzag_pivots(highs[start:], lows[start:], p["zigzag_pct"])
            if len(minima) < p["min_support"] or len(maxima) < p["min_resistance"]:
                continue
            slope_lo, intercept_lo, r2_lo = _fit_line(minima)
            slope_hi, intercept_hi, r2_hi = _fit_line(maxima)
            if slope_lo is None or slope_hi is None or slope_lo <= 0 or slope_hi <= 0:
                continue
            avg_price = float(np.mean(closes[start:]))
            norm_slope = slope_lo / avg_price
            if not (p["slope_min"] <= norm_slope <= p["slope_max"]):
                continue
            # Both rails must be well-defined straight lines, not a loose scatter.
            if r2_lo < p["r_squared_min"] or r2_hi < p["r_squared_hi_min"]:
                continue
            ratio = slope_hi / slope_lo if abs(slope_lo) > 1e-10 else 999
            if not (1 - p["parallelism"] <= ratio <= 1 + p["parallelism"]):
                continue
            last_idx = length - 1
            lo_val = slope_lo * last_idx + intercept_lo
            hi_val = slope_hi * last_idx + intercept_hi
            if hi_val <= lo_val or lo_val <= 0:
                continue
            width = (hi_val - lo_val) / lo_val
            if not (p["width_min"] <= width <= p["width_max"]):
                continue
            cur = float(closes[-1])
            pos = (cur - lo_val) / (hi_val - lo_val)
            if pos > p["position_max"] or pos < -0.05:
                continue

            # Price must actually live inside the channel for most of the window.
            idx = np.arange(length, dtype=float)
            lo_line = slope_lo * idx + intercept_lo
            hi_line = slope_hi * idx + intercept_hi
            tol = p["tolerance"]
            seg_close = closes[start:]
            inside = np.sum((seg_close >= lo_line * (1 - tol)) & (seg_close <= hi_line * (1 + tol)))
            containment = inside / length
            if containment < p["containment_min"]:
                continue

            annual_return = norm_slope * 52
            score = (
                (1 - pos) * 25
                + min(r2_lo, 0.99) * 20
                + min(r2_hi, 0.99) * 10
                + min(len(minima), 5) * 6
                + min(annual_return, 1.0) * 20
                + containment * 15
            )
            if score > best_score:
                best_score = score
                best = {
                    "price": round(cur, 2),
                    "lower_rail": round(lo_val, 2),
                    "upper_rail": round(hi_val, 2),
                    "width_pct": round(width * 100, 1),
                    "position_pct": round(pos * 100, 1),
                    "weeks": length,
                    "annual_return_pct": round(annual_return * 100, 1),
                    "r_squared": round(r2_lo, 3),
                    "r_squared_hi": round(r2_hi, 3),
                    "containment_pct": round(containment * 100, 1),
                    "support_touches": len(minima),
                    "resistance_touches": len(maxima),
                    "score": round(score, 1),
                    "start_date": data.iloc[start]["date"].strftime("%Y-%m-%d"),
                    "end_date": data.iloc[-1]["date"].strftime("%Y-%m-%d"),
                }
        return ScanResult(bool(best), self.name, best or {})

