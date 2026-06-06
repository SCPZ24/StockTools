from __future__ import annotations

import argparse

from stocktools.cli.common import db_path, valid_code
from stocktools.output.csv_writer import write_csv
from stocktools.output.display import print_detail, print_rows
from stocktools.services.hold_service import HoldService


def register(subparsers) -> None:
    parser = subparsers.add_parser("hold", help="管理持仓")
    actions = parser.add_subparsers(dest="hold_cmd", required=True)
    in_cmd = actions.add_parser("in")
    in_cmd.add_argument("code", type=valid_code)
    in_cmd.add_argument("--price", type=float, required=True)
    in_cmd.add_argument("--stop", type=float)
    in_cmd.add_argument("--target", type=float)
    in_cmd.add_argument("--note")
    in_cmd.set_defaults(func=handle_in)
    out = actions.add_parser("out")
    out.add_argument("code", type=valid_code)
    out.add_argument("--price", type=float, required=True)
    out.add_argument("--dec", action="store_true")
    out.set_defaults(func=handle_out)
    set_cmd = actions.add_parser("set")
    set_cmd.add_argument("code", type=valid_code)
    set_cmd.add_argument("--stop", type=float)
    set_cmd.add_argument("--target", type=float)
    set_cmd.add_argument("--note")
    set_cmd.set_defaults(func=handle_set)
    show = actions.add_parser("show")
    show.add_argument("code", type=valid_code)
    show.set_defaults(func=handle_show)
    actions.add_parser("list").set_defaults(func=handle_list)
    hist = actions.add_parser("history")
    hist.add_argument("--near", type=int)
    hist.add_argument("--csv", dest="csv_path")
    hist.set_defaults(func=handle_history)


def handle_in(args):
    row = HoldService(db_path()).add_entry(args.code, args.price, args.stop, args.target, args.note)
    print_detail(row)
    return 0


def handle_out(args):
    count = HoldService(db_path()).exit(args.code, args.price, args.dec)
    print(f"已处理 {count} 条持仓。")
    return 0


def handle_set(args):
    count = HoldService(db_path()).set_fields(args.code, args.stop, args.target, args.note)
    print(f"已更新 {count} 条持仓。")
    return 0


def handle_show(args):
    print_rows(HoldService(db_path()).show(args.code), "没有 open 持仓。")
    return 0


def handle_list(args):
    print_rows(HoldService(db_path()).list_open(), "当前没有持仓。")
    return 0


def handle_history(args):
    rows = HoldService(db_path()).history(args.near)
    print_rows(rows, "没有历史记录。")
    if args.csv_path and rows:
        write_csv(rows, args.csv_path)
        print(f"CSV 已导出: {args.csv_path}")
    return 0
