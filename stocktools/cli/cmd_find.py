from __future__ import annotations

import argparse

from stocktools.cli.common import add_thresholds, compact_options, db_path
from stocktools.output.csv_writer import write_csv
from stocktools.output.display import print_rows
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
    "range_max",
    "support_lift_min",
    "excess_return_min",
    "drawdown_max",
    "recent_return_min",
]


def register(subparsers) -> None:
    parser = subparsers.add_parser("find", help="执行形态扫描")
    parser.add_argument("scanner", choices=scanner_names())
    parser.add_argument("--csv", dest="csv_path")
    add_thresholds(parser, THRESHOLDS)
    parser.set_defaults(func=handle)


def handle(args: argparse.Namespace) -> int:
    options = compact_options(args, THRESHOLDS)
    rows = FindService(db_path()).scan(args.scanner, options)
    print_rows(rows, "没有找到符合条件的股票。")
    if args.csv_path and rows:
        write_csv(rows, args.csv_path)
        print(f"CSV 已导出: {args.csv_path}")
    return 0
