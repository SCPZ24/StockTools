"""低位箱体突破检测

在周线上寻找横盘整理箱体，价格触碰上沿时视为潜在突破。
"""

import numpy as np
import pandas as pd

from config import BOX_DEFAULTS


def detect(df: pd.DataFrame, **overrides) -> dict | None:
    """
    检测最新箱体结构。

    Parameters
    ----------
    df : 周线 DataFrame，至少包含 date/open/high/low/close/volume
    **overrides : 覆盖 BOX_DEFAULTS 中的任何参数

    Returns
    -------
    dict  命中时返回箱体指标
    None  未命中
    """
    p = {**BOX_DEFAULTS, **overrides}

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    n = len(closes)

    if n < p["min_weeks"]:
        return None

    best, best_score = None, 0.0

    for end_idx in range(n - 1, p["min_weeks"] - 1, -1):
        if n - 1 - end_idx > 4:
            break

        for start_idx in range(max(0, end_idx - p["max_weeks"]),
                               end_idx - p["min_weeks"] + 1):
            box_len = end_idx - start_idx + 1
            seg_high = highs[start_idx:end_idx + 1]
            seg_low = lows[start_idx:end_idx + 1]
            box_top = float(np.max(seg_high))
            box_bottom = float(np.min(seg_low))

            height = (box_top - box_bottom) / box_bottom
            if not (p["height_min"] <= height <= p["height_max"]):
                continue

            thr = 0.02
            top_touches = int(np.sum(seg_high >= box_top * (1 - thr)))
            bot_touches = int(np.sum(seg_low <= box_bottom * (1 + thr)))
            if top_touches < p["min_touches"] or bot_touches < p["min_touches"]:
                continue

            cur = float(closes[end_idx])
            pos = (cur - box_bottom) / (box_top - box_bottom)
            if pos < p["position_min"]:
                continue

            decline = 0.0
            if start_idx > 0:
                prior = closes[max(0, start_idx - p["min_weeks"]):start_idx]
                if len(prior) >= 4:
                    peak = float(np.max(prior))
                    decline = (peak - box_bottom) / peak

            yang_vol, yin_vol = [], []
            for i in range(start_idx, end_idx + 1):
                v = float(df.iloc[i]["volume"])
                if df.iloc[i]["close"] >= df.iloc[i]["open"]:
                    yang_vol.append(v)
                else:
                    yin_vol.append(v)

            if yang_vol and yin_vol:
                vr = np.mean(yang_vol) / np.mean(yin_vol)
                if vr < p["vol_ratio_min"]:
                    continue
            else:
                vr = 1.0

            score = (
                pos * 30
                + min(top_touches + bot_touches, 8) * 5
                + max(0, 30 - abs(box_len - 16)) * 1.5
                + min(vr, 2.0) * 10
                + min(decline, 0.5) * 40
            )

            if score > best_score:
                best_score = score
                best = {
                    "start_date": df.iloc[start_idx]["date"].strftime("%Y-%m-%d"),
                    "end_date": df.iloc[end_idx]["date"].strftime("%Y-%m-%d"),
                    "weeks": box_len,
                    "top": round(box_top, 2),
                    "bottom": round(box_bottom, 2),
                    "height_pct": round(height * 100, 1),
                    "price": round(cur, 2),
                    "position_pct": round(pos * 100, 1),
                    "top_touches": top_touches,
                    "bottom_touches": bot_touches,
                    "vol_ratio": round(vr, 2),
                    "decline_pct": round(decline * 100, 1),
                    "score": round(score, 1),
                }

        if best is not None:
            break

    return best
