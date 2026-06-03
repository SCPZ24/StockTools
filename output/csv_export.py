"""CSV 导出"""

import pandas as pd

BOX_COLUMNS = [
    "code", "name", "price", "bottom", "top",
    "height_pct", "position_pct", "weeks",
    "top_touches", "bottom_touches", "vol_ratio",
    "decline_pct", "score", "start_date", "end_date",
]

CHANNEL_COLUMNS = [
    "code", "name", "price", "lower_rail", "upper_rail",
    "width_pct", "position_pct", "weeks",
    "slope_weekly_pct", "annual_return_pct", "r_squared",
    "support_touches", "resistance_touches", "vol_ratio",
    "score", "start_date", "end_date",
]


def export(results: list[dict], path: str, columns: list[str] | None = None):
    if not results:
        print("  无结果可导出。")
        return
    df = pd.DataFrame(results)
    if columns:
        df = df[[c for c in columns if c in df.columns]]
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  结果已导出: {path}")
