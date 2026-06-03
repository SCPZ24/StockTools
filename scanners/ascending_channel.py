"""上升通道检测

用 zigzag 找局部高低点 → 线性回归拟合上下轨 → 验证通道有效性。
当前价格在通道下半部时视为买点。
"""

import numpy as np
import pandas as pd

from config import CHANNEL_DEFAULTS


# ── zigzag 与拟合 ─────────────────────────────────────


def _zigzag_pivots(
    highs: np.ndarray, lows: np.ndarray, pct: float
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """
    返回 (minima, maxima)，每个元素是 (bar_index, price)。
    pct: 转折阈值（如 0.05 = 5%）。
    """
    n = len(highs)
    if n < 3:
        return [], []

    pivots: list[tuple[int, int, float]] = []  # (idx, direction, price)
    last_val = lows[0]
    last_idx = 0
    last_dir = -1  # -1=low, +1=high

    for i in range(1, n):
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

    minima = [(idx, val) for idx, d, val in pivots if d == -1]
    maxima = [(idx, val) for idx, d, val in pivots if d == 1]
    return minima, maxima


def _fit_line(points: list[tuple[int, float]]) -> tuple[float | None, float | None, float]:
    """对 [(index, value), …] 做最小二乘，返回 (slope, intercept, r²)。"""
    if len(points) < 2:
        return None, None, 0.0

    x = np.array([p[0] for p in points], dtype=float)
    y = np.array([p[1] for p in points], dtype=float)

    n = len(x)
    sx, sy = x.sum(), y.sum()
    sxx, sxy = (x * x).sum(), (x * y).sum()
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-10:
        return None, None, 0.0

    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n

    y_pred = slope * x + intercept
    ss_res = ((y - y_pred) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot > 1e-10 else 0.0

    return slope, intercept, r2


# ── 主检测 ────────────────────────────────────────────


def detect(df: pd.DataFrame, **overrides) -> dict | None:
    """
    检测上升通道。

    Parameters
    ----------
    df : 周线 DataFrame
    **overrides : 覆盖 CHANNEL_DEFAULTS 中的任何参数

    Returns
    -------
    dict  命中时返回通道指标
    None  未命中
    """
    p = {**CHANNEL_DEFAULTS, **overrides}

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    n = len(closes)

    if n < p["min_weeks"]:
        return None

    best, best_score = None, 0.0

    for length in range(min(p["max_weeks"], n), p["min_weeks"] - 1, -2):
        start = n - length
        seg_h = highs[start:]
        seg_l = lows[start:]
        seg_c = closes[start:]

        minima, maxima = _zigzag_pivots(seg_h, seg_l, p["zigzag_pct"])

        if len(minima) < 3 or len(maxima) < 2:
            continue

        slope_lo, intercept_lo, r2_lo = _fit_line(minima)
        slope_hi, intercept_hi, r2_hi = _fit_line(maxima)

        if slope_lo is None or slope_hi is None:
            continue
        if slope_lo <= 0 or slope_hi <= 0:
            continue

        avg_price = float(np.mean(seg_c))
        norm_slope = slope_lo / avg_price
        if not (p["slope_min"] <= norm_slope <= p["slope_max"]):
            continue

        if r2_lo < p["r_squared_min"]:
            continue

        ratio = slope_hi / slope_lo if abs(slope_lo) > 1e-10 else 999.0
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

        cur = float(seg_c[-1])
        pos = (cur - lo_val) / (hi_val - lo_val)
        if pos > p["position_max"] or pos < -0.05:
            continue

        yang_vol, yin_vol = [], []
        for i in range(len(seg_c)):
            v = float(df.iloc[start + i]["volume"])
            if df.iloc[start + i]["close"] >= df.iloc[start + i]["open"]:
                yang_vol.append(v)
            else:
                yin_vol.append(v)
        vr = np.mean(yang_vol) / np.mean(yin_vol) if (yang_vol and yin_vol) else 1.0

        annual_return = norm_slope * 52
        score = (
            (1 - pos) * 30
            + min(r2_lo, 0.99) * 25
            + min(len(minima), 5) * 8
            + min(vr, 2.0) * 10
            + min(annual_return, 1.0) * 20
        )

        if score > best_score:
            best_score = score
            best = {
                "start_date": df.iloc[start]["date"].strftime("%Y-%m-%d"),
                "end_date": df.iloc[n - 1]["date"].strftime("%Y-%m-%d"),
                "weeks": length,
                "price": round(cur, 2),
                "lower_rail": round(lo_val, 2),
                "upper_rail": round(hi_val, 2),
                "width_pct": round(width * 100, 1),
                "position_pct": round(pos * 100, 1),
                "slope_weekly_pct": round(norm_slope * 100, 2),
                "annual_return_pct": round(annual_return * 100, 1),
                "r_squared": round(r2_lo, 3),
                "support_touches": len(minima),
                "resistance_touches": len(maxima),
                "vol_ratio": round(vr, 2),
                "score": round(score, 1),
            }

    return best
