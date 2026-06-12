from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseScanner
from .results import ScanResult
from .utils import normalize_df

DEFAULTS = {
    "ma_periods": (5, 10, 20, 30, 60),
    "lookback": 120,
    "order_days_min": 5,
    "slope_lookback": 5,
    "vol_ma_period": 10,
    "vol_ratio_min": 1.0,
    "divergence_lookback": 10,
    "ma60_gap_max": 0.30,
    "ma60_slope_min": 0.01,
    "gap_min_pct": 0.005,
    "spread_max_pct": 0.20,
    "ma5_tolerance": 0.05,
}


def _sma(series: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average. Uncomputed leading entries = NaN."""
    out = np.full(len(series), np.nan)
    if len(series) < period:
        return out
    cumsum = np.cumsum(np.insert(series, 0, 0.0))
    out[period - 1 :] = (cumsum[period:] - cumsum[:-period]) / period
    return out


def _pct_change(curr: float, prev: float) -> float:
    """Safe percentage change. Returns 0 if prev ≤ 0."""
    return (curr - prev) / prev if prev > 0 else 0.0


class MAAlignmentScanner(BaseScanner):
    """Detect MA multi-head uniform-divergence patterns (均线多头排列 – 均匀发散).

    Conditions (all must pass):
      1. MA order: MA5 > MA10 > MA20 > MA30 > MA60
      2. The order above must hold for at least ``order_days_min`` consecutive days.
      3. Every MA has positive slope over ``slope_lookback`` days; MA60 slope ≥ ``ma60_slope_min``.
      4. Total MA5−MA60 spread must be widening (≥2% over ``divergence_lookback`` days).
      5. No two MAs are stuck together (min gap ≥ ``gap_min_pct`` × price).
      6. Total MA5–MA60 spread ≤ ``spread_max_pct`` × price (not over-extended).
      7. Price > all MAs and price − MA60 ≤ ``ma60_gap_max``.
      8. Recent volume > volume SMA (volume expansion confirmation).
    """

    name = "ma_alignment"
    label = "MA均线多头排列"

    # ── detect ───────────────────────────────────────────────────
    def detect(self, df: pd.DataFrame, **kwargs) -> ScanResult:
        p = {**DEFAULTS, **kwargs}
        data = normalize_df(df)
        periods = tuple(p["ma_periods"])
        max_period = max(periods)
        min_data = max(int(p["lookback"]), max_period + 20)

        if len(data) < min_data:
            return ScanResult(False, self.name)

        closes = data["close"].values
        volumes = data["volume"].values
        dates = data["date"].values
        n = len(closes)
        latest = n - 1

        # ── compute all MAs ──────────────────────────────────────
        mas: dict[int, np.ndarray] = {}
        for prd in periods:
            mas[prd] = _sma(closes, prd)

        def ma_val(prd: int, idx: int) -> float:
            return float(mas[prd][idx])

        # ── 1. MA order at latest bar ────────────────────────────
        ma_now = [ma_val(prd, latest) for prd in periods]
        if any(np.isnan(v) for v in ma_now):
            return ScanResult(False, self.name)
        for i in range(len(periods) - 1):
            if ma_now[i] <= ma_now[i + 1]:
                return ScanResult(False, self.name)

        # ── 2. consecutive days with correct order ────────────────
        order_min = int(p["order_days_min"])
        consecutive = 0
        for i in range(latest, max(0, latest - int(p["lookback"])), -1):
            vals = [ma_val(prd, i) for prd in periods]
            if any(np.isnan(v) for v in vals):
                break
            if all(vals[j] > vals[j + 1] for j in range(len(periods) - 1)):
                consecutive += 1
            else:
                break
        if consecutive < order_min:
            return ScanResult(False, self.name)

        # ── 3. MA slopes (all positive) ──────────────────────────
        slope_lb = int(p["slope_lookback"])
        if latest - slope_lb < 0:
            return ScanResult(False, self.name)

        slopes: dict[int, float] = {}
        for prd in periods:
            prev = ma_val(prd, latest - slope_lb)
            curr = ma_val(prd, latest)
            if np.isnan(prev) or np.isnan(curr):
                return ScanResult(False, self.name)
            slopes[prd] = _pct_change(curr, prev)

        if any(s <= 0 for s in slopes.values()):
            return ScanResult(False, self.name)
        if slopes[60] < float(p["ma60_slope_min"]):
            return ScanResult(False, self.name)

        # ── 4. divergence: total spread must widen ────────────────
        div_lb = int(p["divergence_lookback"])
        if latest - div_lb < 0:
            return ScanResult(False, self.name)

        cur_price = float(closes[latest])
        if cur_price <= 0:
            return ScanResult(False, self.name)

        def _spread(idx: int) -> float:
            """MA5−MA60 spread normalised by current price."""
            return (ma_val(5, idx) - ma_val(60, idx)) / cur_price

        spread_now = _spread(latest)
        spread_past = _spread(latest - div_lb)
        spread_ratio = spread_now / spread_past if spread_past > 0 else 1.0
        if spread_ratio < 1.02:  # must widen ≥2%
            return ScanResult(False, self.name)

        # Compute per-gap info (for scoring and gap checks, not as hard gate)
        def _gaps(idx: int) -> list[float]:
            vs = [ma_val(prd, idx) for prd in periods]
            return [(vs[i] - vs[i + 1]) / cur_price for i in range(len(periods) - 1)]

        gaps_now = _gaps(latest)
        widened_count = sum(
            1 for i in range(len(gaps_now))
            if gaps_now[i] > _gaps(latest - div_lb)[i] * 0.95
        )

        # ── 5. minimum gap (no clustering) ───────────────────────
        gap_min = float(p["gap_min_pct"])
        if min(gaps_now) < gap_min:
            return ScanResult(False, self.name)

        # ── 6. total spread not too wide ─────────────────────────
        total_spread = (ma_now[0] - ma_now[-1]) / cur_price
        if total_spread > float(p["spread_max_pct"]):
            return ScanResult(False, self.name)

        # ── 7. price vs MAs ──────────────────────────────────────
        ma5_val = ma_now[0]
        ma5_tol = float(p["ma5_tolerance"])
        if cur_price < ma5_val * (1 - ma5_tol):
            return ScanResult(False, self.name)
        for prd in periods[1:]:  # MA10/20/30/60
            if cur_price <= ma_val(prd, latest):
                return ScanResult(False, self.name)

        ma60_val = ma_val(60, latest)
        gap_ma60 = _pct_change(cur_price, ma60_val)
        if gap_ma60 > float(p["ma60_gap_max"]):
            return ScanResult(False, self.name)

        # ── 8. volume expansion ──────────────────────────────────
        vol_ma = _sma(volumes, int(p["vol_ma_period"]))
        recent_vol = float(np.mean(volumes[latest - 4 : latest + 1]))
        vol_ma_val = float(vol_ma[latest])
        if np.isnan(vol_ma_val) or vol_ma_val <= 0:
            return ScanResult(False, self.name)
        vol_ratio = recent_vol / vol_ma_val
        if vol_ratio < float(p["vol_ratio_min"]):
            return ScanResult(False, self.name)

        # ── scoring ──────────────────────────────────────────────
        divergence_quality = widened_count / len(gaps_now)
        gap_score = divergence_quality * 25
        order_score = min(consecutive / 20.0, 1.0) * 20
        vol_score = min(vol_ratio / 2.0, 1.0) * 15
        slope_score = min(slopes[60] / 0.05, 1.0) * 15
        safety_score = max(1.0 - gap_ma60 / 0.30, 0) * 15
        spread_quality = min(spread_ratio / 1.10, 1.0) * 10

        score = gap_score + order_score + vol_score + slope_score + safety_score + spread_quality

        return ScanResult(
            True,
            self.name,
            {
                "price": round(cur_price, 2),
                "ma5": round(ma_now[0], 2),
                "ma10": round(ma_now[1], 2),
                "ma20": round(ma_now[2], 2),
                "ma30": round(ma_now[3], 2),
                "ma60": round(ma60_val, 2),
                "ma60_gap_pct": round(gap_ma60 * 100, 1),
                "order_days": consecutive,
                "vol_ratio": round(vol_ratio, 2),
                "score": round(score, 1),
                "date": pd.Timestamp(dates[latest]).strftime("%Y-%m-%d"),
            },
        )
