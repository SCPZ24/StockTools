from __future__ import annotations

import pandas as pd

from .base import BaseScanner
from .results import ScanResult
from .utils import max_drawdown, normalize_df


class IndependentScanner(BaseScanner):
    name = "independent"
    label = "独立行情"

    def detect(self, df: pd.DataFrame, **kwargs) -> ScanResult:
        excess_return_min = float(kwargs.get("excess_return_min", 0.15))
        drawdown_max = float(kwargs.get("drawdown_max", 0.25))
        recent_return_min = float(kwargs.get("recent_return_min", 0.0))
        baseline_return = float(kwargs.get("baseline_return", 0.0))
        data = normalize_df(df)
        if len(data) < 120:
            return ScanResult(False, self.name)
        last60 = data.tail(60)
        last20 = data.tail(20)
        start60 = float(last60.iloc[0]["close"])
        start20 = float(last20.iloc[0]["close"])
        latest = float(data.iloc[-1]["close"])
        if start60 <= 0 or start20 <= 0:
            return ScanResult(False, self.name)
        ret60 = latest / start60 - 1
        ret20 = latest / start20 - 1
        excess = ret60 - baseline_return
        dd = max_drawdown(last60["close"].values)
        matched = excess >= excess_return_min and dd <= drawdown_max and ret20 >= recent_return_min
        indicators = {
            "price": round(latest, 2),
            "return_60d_pct": round(ret60 * 100, 1),
            "baseline_return_pct": round(baseline_return * 100, 1),
            "excess_return_pct": round(excess * 100, 1),
            "return_20d_pct": round(ret20 * 100, 1),
            "max_drawdown_pct": round(dd * 100, 1),
            "score": round(excess * 100 - dd * 30 + ret20 * 20, 1),
        }
        return ScanResult(matched, self.name, indicators if matched else {})

