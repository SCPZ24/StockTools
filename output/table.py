"""终端表格打印"""

from datetime import datetime


def print_box_results(results: list[dict], pool: str, stock_count: int, params: dict):
    if not results:
        print("\n没有找到符合条件的箱体结构。")
        return

    print(f"\n{'='*115}")
    print(f"  低位箱体突破扫描  {datetime.now():%Y-%m-%d %H:%M}")
    print(f"  池={pool}({stock_count}只)  "
          f"高度{params['height_min']*100:.0f}-{params['height_max']*100:.0f}%  "
          f"触碰≥{params['min_touches']}  "
          f"位≥{params['position_min']*100:.0f}%  "
          f"跌≥{params['decline_min']*100:.0f}%  "
          f"量比≥{params['vol_ratio_min']}")
    print(f"{'='*115}\n")

    header = (f"  {'代码':<10} {'名称':<10} {'现价':>8} {'下沿':>8} {'上沿':>8} "
              f"{'高%':>5} {'位%':>5} {'周':>4} {'触碰':>8} {'阳/阴':>6} "
              f"{'跌%':>5} {'得分':>6}")
    print(header)
    print(f"  {'-'*108}")

    for r in results:
        print(f"  {r['code']:<10} {r['name']:<10} {r['price']:>8.2f} "
              f"{r['bottom']:>8.2f} {r['top']:>8.2f} "
              f"{r['height_pct']:>4.1f}% {r['position_pct']:>4.1f}% "
              f"{r['weeks']:>3}周 {r['top_touches']}↑/{r['bottom_touches']}↓ "
              f"{r['vol_ratio']:>4.1f}x {r['decline_pct']:>4.0f}% {r['score']:>6.1f}")

    print(f"\n  仅为形态筛选，不构成投资建议。")


def print_channel_results(results: list[dict], pool: str, stock_count: int, params: dict):
    if not results:
        print("\n没有找到符合条件的上升通道。")
        return

    print(f"\n{'='*120}")
    print(f"  上升通道扫描  {datetime.now():%Y-%m-%d %H:%M}")
    print(f"  池={pool}({stock_count}只)  "
          f"宽度{params['width_min']*100:.0f}-{params['width_max']*100:.0f}%  "
          f"R²≥{params['r_squared_min']}  "
          f"位≤{params['position_max']*100:.0f}%")
    print(f"{'='*120}\n")

    header = (f"  {'代码':<10} {'名称':<10} {'现价':>8} {'下轨':>8} {'上轨':>8} "
              f"{'宽%':>5} {'位%':>5} {'周':>4} {'年化%':>6} {'R²':>6} "
              f"{'支撑':>4} {'阳/阴':>6} {'得分':>6}")
    print(header)
    print(f"  {'-'*113}")

    for r in results:
        print(f"  {r['code']:<10} {r['name']:<10} {r['price']:>8.2f} "
              f"{r['lower_rail']:>8.2f} {r['upper_rail']:>8.2f} "
              f"{r['width_pct']:>4.1f}% {r['position_pct']:>4.1f}% "
              f"{r['weeks']:>3}周 {r['annual_return_pct']:>5.1f}% "
              f"{r['r_squared']:>5.3f} "
              f"{r['support_touches']:>3}次 "
              f"{r['vol_ratio']:>4.1f}x {r['score']:>6.1f}")

    print(f"\n  仅为形态筛选，不构成投资建议。")
