from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseScanner
from .results import ScanResult
from .utils import normalize_df

DEFAULTS = {
    "fixed_window": 25,
    "height_min": 0.05,
    "height_max": 0.22,
    "min_touches": 2,
    "touch_tolerance": 0.05,
    "decline_min": 0.20,
    "position_min": 0.55,
    "position_max": 1.08,
    "vol_ratio_min": 0.8,
    "containment_min": 0.90,
    "flat_max": 0.10,
    "range_pos_max": 0.50,
}


def _percentile_linear(values: np.ndarray, q: float) -> float:
    sorted_values = np.sort(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * q / 100
    lower = int(pos)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = pos - lower
    return float(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight)


def _drift(seg_close: np.ndarray) -> float:
    """Total trend drift across the segment, normalised by mean price.

    A genuine box is horizontal, so |drift| should be small. A value of
    0.10 means the regression line rises/falls 10% of price end-to-end."""
    n = len(seg_close)
    if n < 3:
        return 0.0
    x = np.arange(n, dtype=float)
    denom = n * (x * x).sum() - x.sum() ** 2
    if abs(denom) < 1e-10:
        return 0.0
    slope = (n * (x * seg_close).sum() - x.sum() * seg_close.sum()) / denom
    avg = float(np.mean(seg_close))
    if avg <= 0:
        return 0.0
    return abs(slope * (n - 1) / avg)


class BoxScanner(BaseScanner):
    name = "box"
    label = "低位箱体整理"

    def detect(self, df: pd.DataFrame, **kwargs) -> ScanResult:
        p = {**DEFAULTS, **kwargs}
        data = normalize_df(df)
        fixed_window = int(p["fixed_window"])
        if len(data) < fixed_window + 1:
            return ScanResult(False, self.name)

        closes = data["close"].values
        opens = data["open"].values
        highs = data["high"].values
        lows = data["low"].values
        volumes = data["volume"].values
        dates = data["date"].values
        n = len(closes)

        # ── 取最后 fixed_window 根 K 线 ──────────────────────────
        start_idx = n - fixed_window
        end_idx = n - 1

        seg_high = highs[start_idx : end_idx + 1]
        seg_low = lows[start_idx : end_idx + 1]
        seg_close = closes[start_idx : end_idx + 1]
        seg_open = opens[start_idx : end_idx + 1]
        seg_volume = volumes[start_idx : end_idx + 1]

        # ── 上下沿：P95 / P5 ──────────────────────────────────────
        box_top = _percentile_linear(seg_high, 95)
        box_bottom = _percentile_linear(seg_low, 5)
        if box_bottom <= 0 or box_top <= box_bottom:
            return ScanResult(False, self.name)
        height = (box_top - box_bottom) / box_bottom
        if not (p["height_min"] <= height <= p["height_max"]):
            return ScanResult(False, self.name)

        # ── 水平性：箱体必须是平的 ────────────────────────────────
        if _drift(seg_close) > p["flat_max"]:
            return ScanResult(False, self.name)

        # ── 历史位置：箱子必须在可见范围的下半部 ──────────────────
        hist_high = float(np.max(highs[: end_idx + 1]))
        hist_low = float(np.min(lows[: end_idx + 1]))
        hist_span = hist_high - hist_low
        if hist_span > 0:
            range_pos = (box_top - hist_low) / hist_span
            if range_pos > p["range_pos_max"]:
                return ScanResult(False, self.name)
        else:
            range_pos = 0.0

        # ── 触碰计数（5% 容差）────────────────────────────────────
        tol = p["touch_tolerance"]
        top_touches = int(np.sum(seg_high >= box_top * (1 - tol)))
        bot_touches = int(np.sum(seg_low <= box_bottom * (1 + tol)))
        if top_touches < p["min_touches"] or bot_touches < p["min_touches"]:
            return ScanResult(False, self.name)

        # ── 包含率：价格要住在箱子里 ──────────────────────────────
        contained = int(
            np.sum(
                (seg_close >= box_bottom * (1 - tol))
                & (seg_close <= box_top * (1 + tol))
            )
        )
        containment = contained / fixed_window
        if containment < p["containment_min"]:
            return ScanResult(False, self.name)

        # ── 前期跌幅：窗口之前的所有数据找峰 ──────────────────────
        if start_idx > 0:
            prior_peak = float(np.max(highs[:start_idx]))
        else:
            prior_peak = box_top
        decline = (
            (prior_peak - box_top) / prior_peak if prior_peak > 0 else 0.0
        )
        if decline < p["decline_min"]:
            return ScanResult(False, self.name)

        # ── 当前位置 ──────────────────────────────────────────────
        cur = float(closes[end_idx])
        pos = (cur - box_bottom) / (box_top - box_bottom)
        if not (p["position_min"] <= pos <= p["position_max"]):
            return ScanResult(False, self.name)

        # ── 量价：阳量 vs 阴量 ────────────────────────────────────
        yang_mask = seg_close >= seg_open
        yin_mask = ~yang_mask
        vr = (
            float(np.mean(seg_volume[yang_mask]) / np.mean(seg_volume[yin_mask]))
            if yang_mask.any() and yin_mask.any()
            else 1.0
        )
        if vr < p["vol_ratio_min"]:
            return ScanResult(False, self.name)

        # ── 综合打分 ──────────────────────────────────────────────
        score = (
            pos * 25
            + min(top_touches + bot_touches, 20) * 3
            + min(vr, 2.0) * 10
            + min(decline, 0.5) * 50
            + containment * 25
            + (1 - _drift(seg_close) / p["flat_max"]) * 15
        )

        return ScanResult(
            True,
            self.name,
            {
                "price": round(cur, 2),
                "bottom": round(box_bottom, 2),
                "top": round(box_top, 2),
                "height_pct": round(height * 100, 1),
                "position_pct": round(pos * 100, 1),
                "days": fixed_window,
                "top_touches": top_touches,
                "bottom_touches": bot_touches,
                "containment_pct": round(containment * 100, 1),
                "vol_ratio": round(vr, 2),
                "decline_pct": round(decline * 100, 1),
                "range_pos_pct": round(range_pos * 100, 1)
                if hist_span > 0
                else 0.0,
                "score": round(score, 1),
                "start_date": pd.Timestamp(dates[start_idx]).strftime("%Y-%m-%d"),
                "end_date": pd.Timestamp(dates[end_idx]).strftime("%Y-%m-%d"),
            },
        )
