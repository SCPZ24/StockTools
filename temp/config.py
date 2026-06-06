"""全局常量与默认参数"""

LOOKBACK_YEARS = 2

# ── 低位箱体突破 ──────────────────────────────────────
BOX_DEFAULTS = {
    "min_weeks": 8,
    "max_weeks": 40,
    "height_min": 0.06,
    "height_max": 0.45,
    "min_touches": 1,
    "decline_min": 0.08,
    "position_min": 0.45,
    "vol_ratio_min": 0.6,
}

# ── 上升通道 ──────────────────────────────────────────
CHANNEL_DEFAULTS = {
    "min_weeks": 10,
    "max_weeks": 52,
    "slope_min": 0.002,        # 周最小斜率 (年化 ≈ 10%)
    "slope_max": 0.02,         # 周最大斜率 (年化 ≈ 180%)
    "width_min": 0.08,         # 通道最小宽度
    "width_max": 0.35,         # 通道最大宽度
    "r_squared_min": 0.75,     # 拟合优度下限
    "parallelism": 0.5,        # 上下轨斜率比偏差允许范围
    "position_max": 0.5,       # 当前在通道中的位置上限 (下半部 = 买点)
    "zigzag_pct": 0.05,        # zigzag 转折阈值
}
