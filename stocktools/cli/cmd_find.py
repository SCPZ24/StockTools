from __future__ import annotations

import argparse

from stocktools.cli.common import add_thresholds, compact_options, db_path
from stocktools.output.csv_writer import write_csv
from stocktools.scanners.registry import scanner_names
from stocktools.services.find_service import FindService


THRESHOLDS = [
    "height_min",
    "height_max",
    "min_touches",
    "decline_min",
    "position_min",
    "vol_ratio_min",
    "width_min",
    "width_max",
    "r_squared_min",
    "position_max",
]


def format_indicator_summary(item: dict, limit: int | None = None) -> str:
    indicators = {k: v for k, v in item.items() if k not in ("code", "name", "pattern")}
    pairs = list(indicators.items()) if limit is None else list(indicators.items())[:limit]
    return "  ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in pairs)


def format_stream_row(item: dict) -> str:
    parts = [item["code"], item.get("name", ""), item.get("pattern", "")]
    summary = format_indicator_summary(item)
    if summary:
        parts.append(summary)
    return "  ".join(str(part) for part in parts)


def register(subparsers) -> None:
    parser = subparsers.add_parser("find", help="执行形态扫描")
    parser.add_argument("scanner", choices=scanner_names())
    parser.add_argument("--csv", dest="csv_path")
    parser.add_argument("--top", dest="top", type=int, default=10, help="只保留评分最高的 N 支（默认 10，0 表示全部）")
    add_thresholds(parser, THRESHOLDS)
    parser.set_defaults(func=handle)


def handle(args: argparse.Namespace) -> int:
    options = compact_options(args, THRESHOLDS)
    rows = []
    for item in FindService(db_path()).iter_scan(args.scanner, options):
        rows.append(item)
        print(format_stream_row(item), flush=True)
    if not rows:
        print("没有找到符合条件的股票。")
        return 0

    rows.sort(key=lambda r: float(r.get("score", 0)), reverse=True)
    top = rows[: args.top] if args.top and args.top > 0 else rows

    print(f"\n扫描完成，共 {len(rows)} 条，评分最高的 {len(top)} 支：")
    for rank, item in enumerate(top, 1):
        print(f"{rank:>2}. {format_stream_row(item)}", flush=True)

    if args.csv_path:
        write_csv(top, args.csv_path)
        print(f"CSV 已导出: {args.csv_path}")
    return 0
