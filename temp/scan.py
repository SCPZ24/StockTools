#!/usr/bin/env python3
"""
A股中线结构扫描器 — 统一入口

用法:
  python scan.py box                               # 低位箱体突破 (默认 csi800)
  python scan.py channel                           # 上升通道
  python scan.py all                               # 两种结构都扫
  python scan.py box --pool all --top 40           # 全A股箱体
  python scan.py channel --export results/ch.csv   # 导出上升通道
  python scan.py box --height-min 0.08 --position 0.6  # 自定义箱体参数
"""

import argparse
import sys
import time
import warnings
from types import ModuleType

from config import BOX_DEFAULTS, CHANNEL_DEFAULTS
from data import BaostockSession, load_stock_list
from scanners import box_breakout, ascending_channel
from output import print_box_results, print_channel_results, export
from output.csv_export import BOX_COLUMNS, CHANNEL_COLUMNS

warnings.filterwarnings("ignore")


# ── 通用扫描循环 ──────────────────────────────────────


def run_scanner(
    session: BaostockSession,
    stocks: list[dict],
    scanner: ModuleType,
    min_weeks: int,
    label: str,
    top: int,
    **scanner_kwargs,
) -> list[dict]:
    results: list[dict] = []
    total = len(stocks)
    t0 = time.time()
    err = 0

    for i, s in enumerate(stocks):
        code, name = s["code"], s["name"]
        raw_code = code.split(".")[1]

        if (i + 1) % 50 == 0 or i == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(
                f"  [{i+1}/{total}] {name}({raw_code}) | "
                f"{label}{len(results)} | 错误{err} | "
                f"{rate:.1f}只/秒 | 剩{eta:.0f}s",
                end="\r", flush=True,
            )

        df = session.query_weekly(code)
        if df is None or len(df) < min_weeks:
            err += 1
            continue

        hit = scanner.detect(df, **scanner_kwargs)
        if hit is None:
            continue

        hit["code"] = raw_code
        hit["name"] = name
        results.append(hit)

    print(f"\n  扫描完成: {total}只 → {label}{len(results)}只 | 错误{err}只")
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top]


# ── CLI ───────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="A股中线结构扫描器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "mode", choices=["box", "channel", "all"],
        help="扫描模式: box=箱体突破  channel=上升通道  all=全部",
    )
    p.add_argument("--pool", default="csi800",
                   choices=["csi300", "csi500", "csi800", "all"])
    p.add_argument("--top", type=int, default=30, help="输出前 N 只 (默认30)")
    p.add_argument("--export", default=None, help="导出 CSV 路径")

    g = p.add_argument_group("箱体参数")
    g.add_argument("--height-min", type=float, default=BOX_DEFAULTS["height_min"])
    g.add_argument("--height-max", type=float, default=BOX_DEFAULTS["height_max"])
    g.add_argument("--touches", type=int, default=BOX_DEFAULTS["min_touches"])
    g.add_argument("--decline", type=float, default=BOX_DEFAULTS["decline_min"])
    g.add_argument("--position", type=float, default=BOX_DEFAULTS["position_min"])
    g.add_argument("--vol-ratio", type=float, default=BOX_DEFAULTS["vol_ratio_min"])

    g2 = p.add_argument_group("通道参数")
    g2.add_argument("--ch-width-min", type=float, default=CHANNEL_DEFAULTS["width_min"])
    g2.add_argument("--ch-width-max", type=float, default=CHANNEL_DEFAULTS["width_max"])
    g2.add_argument("--ch-r2", type=float, default=CHANNEL_DEFAULTS["r_squared_min"])
    g2.add_argument("--ch-position", type=float, default=CHANNEL_DEFAULTS["position_max"])

    return p


def main():
    args = build_parser().parse_args()

    box_kw = {
        "height_min": args.height_min,
        "height_max": args.height_max,
        "min_touches": args.touches,
        "decline_min": args.decline,
        "position_min": args.position,
        "vol_ratio_min": args.vol_ratio,
    }
    ch_kw = {
        "width_min": args.ch_width_min,
        "width_max": args.ch_width_max,
        "r_squared_min": args.ch_r2,
        "position_max": args.ch_position,
    }

    print(f"\n  A股中线结构扫描器")
    print(f"  模式: {args.mode}  股票池: {args.pool}\n")

    with BaostockSession() as session:
        print("▶ 获取股票列表...")
        stocks = load_stock_list(session, args.pool)
        stock_count = len(stocks)

        # ── 箱体突破 ──
        if args.mode in ("box", "all"):
            print(f"\n▶ 扫描低位箱体突破 ({stock_count}只)...")
            box_results = run_scanner(
                session, stocks, box_breakout,
                BOX_DEFAULTS["min_weeks"], "箱体", args.top,
                **box_kw,
            )
            print_box_results(box_results, args.pool, stock_count, {**BOX_DEFAULTS, **box_kw})
            if args.export and box_results:
                path = args.export if args.mode == "box" else args.export.replace(".csv", "_box.csv")
                export(box_results, path, BOX_COLUMNS)

        # ── 上升通道 ──
        if args.mode in ("channel", "all"):
            print(f"\n▶ 扫描上升通道 ({stock_count}只)...")
            ch_results = run_scanner(
                session, stocks, ascending_channel,
                CHANNEL_DEFAULTS["min_weeks"], "通道", args.top,
                **ch_kw,
            )
            print_channel_results(ch_results, args.pool, stock_count, {**CHANNEL_DEFAULTS, **ch_kw})
            if args.export and ch_results:
                path = args.export if args.mode == "channel" else args.export.replace(".csv", "_channel.csv")
                export(ch_results, path, CHANNEL_COLUMNS)


if __name__ == "__main__":
    main()
