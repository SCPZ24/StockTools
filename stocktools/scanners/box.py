from __future__ import annotations

import numpy as np
import pandas as pd

from .base import BaseScanner
from .results import ScanResult
from .utils import weekly_df


DEFAULTS = {
    "min_weeks": 8,
    "max_weeks": 40,
    "height_min": 0.06,
    "height_max": 0.45,
    "min_touches": 2,
    "touch_tolerance": 0.03,
    "decline_min": 0.08,
    "position_min": 0.45,
    "vol_ratio_min": 0.6,
    "containment_min": 0.75,
}


class BoxScanner(BaseScanner):
    name = "box"
    label = "低位箱体整理"

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

        for end_idx in range(n - 1, p["min_weeks"] - 1, -1):
            if n - 1 - end_idx > 4:
                break
            for start_idx in range(max(0, end_idx - p["max_weeks"]), end_idx - p["min_weeks"] + 1):
                box_len = end_idx - start_idx + 1
                seg_high = highs[start_idx : end_idx + 1]
                seg_low = lows[start_idx : end_idx + 1]
                seg_close = closes[start_idx : end_idx + 1]

                box_top = float(np.percentile(seg_high, 95))
                box_bottom = float(np.percentile(seg_low, 5))
                if box_bottom <= 0 or box_top <= box_bottom:
                    continue
                height = (box_top - box_bottom) / box_bottom
                if not (p["height_min"] <= height <= p["height_max"]):
                    continue

                tol = p["touch_tolerance"]
                top_touches = int(np.sum(seg_high >= box_top * (1 - tol)))
                bot_touches = int(np.sum(seg_low <= box_bottom * (1 + tol)))
                if top_touches < p["min_touches"] or bot_touches < p["min_touches"]:
                    continue

                contained = int(np.sum((seg_close >= box_bottom * (1 - tol)) & (seg_close <= box_top * (1 + tol))))
                containment = contained / box_len
                if containment < p["containment_min"]:
                    continue

                decline = 0.0
                if start_idx > 0:
                    prior = closes[max(0, start_idx - p["min_weeks"]) : start_idx]
                    if len(prior) >= 4:
                        peak = float(np.max(prior))
                        decline = (peak - box_bottom) / peak if peak > 0 else 0.0
                if decline < p["decline_min"] and start_idx > 0:
                    continue

                cur = float(closes[end_idx])
                pos = (cur - box_bottom) / (box_top - box_bottom)
                if pos < p["position_min"]:
                    continue

                yang_vol, yin_vol = [], []
                for i in range(start_idx, end_idx + 1):
                    row = data.iloc[i]
                    if row["close"] >= row["open"]:
                        yang_vol.append(float(row["volume"]))
                    else:
                        yin_vol.append(float(row["volume"]))
                vr = float(np.mean(yang_vol) / np.mean(yin_vol)) if yang_vol and yin_vol else 1.0
                if vr < p["vol_ratio_min"]:
                    continue

                score = (
                    pos * 30
                    + min(top_touches + bot_touches, 8) * 5
                    + max(0, 30 - abs(box_len - 16)) * 1.5
                    + min(vr, 2.0) * 10
                    + min(decline, 0.5) * 40
                    + containment * 20
                )
                if score > best_score:
                    best_score = score
                    best = {
                        "price": round(cur, 2),
                        "bottom": round(box_bottom, 2),
                        "top": round(box_top, 2),
                        "height_pct": round(height * 100, 1),
                        "position_pct": round(pos * 100, 1),
                        "weeks": box_len,
                        "top_touches": top_touches,
                        "bottom_touches": bot_touches,
                        "containment_pct": round(containment * 100, 1),
                        "vol_ratio": round(vr, 2),
                        "decline_pct": round(decline * 100, 1),
                        "score": round(score, 1),
                        "start_date": data.iloc[start_idx]["date"].strftime("%Y-%m-%d"),
                        "end_date": data.iloc[end_idx]["date"].strftime("%Y-%m-%d"),
                    }
            if best:
                break
        return ScanResult(bool(best), self.name, best or {})
