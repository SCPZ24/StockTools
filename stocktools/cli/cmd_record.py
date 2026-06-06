from __future__ import annotations

import argparse

from stocktools.cli.common import db_path, valid_code
from stocktools.output.display import print_detail, print_rows
from stocktools.services.record_service import RecordService


def register(subparsers) -> None:
    parser = subparsers.add_parser("record", help="管理关注池")
    actions = parser.add_subparsers(dest="record_cmd", required=True)
    add = actions.add_parser("add")
    add.add_argument("code", type=valid_code)
    add.add_argument("-m", "--message")
    add.set_defaults(func=handle_add)
    show = actions.add_parser("show")
    show.add_argument("code", type=valid_code)
    show.set_defaults(func=handle_show)
    note = actions.add_parser("note")
    note.add_argument("code", type=valid_code)
    note.add_argument("message")
    note.add_argument("--replace", action="store_true")
    note.set_defaults(func=handle_note)
    go = actions.add_parser("go")
    go.add_argument("code", type=valid_code)
    go.set_defaults(func=handle_go)
    actions.add_parser("list").set_defaults(func=handle_list)
    rm = actions.add_parser("rm")
    rm.add_argument("code", type=valid_code)
    rm.set_defaults(func=handle_rm)


def handle_add(args):
    row = RecordService(db_path()).add(args.code, args.message)
    print_detail(row)
    return 0


def handle_show(args):
    print_detail(RecordService(db_path()).show(args.code), "关注池中没有这只股票。")
    return 0


def handle_note(args):
    print_detail(RecordService(db_path()).note(args.code, args.message, args.replace))
    return 0


def handle_go(args):
    print_detail(RecordService(db_path()).go(args.code))
    return 0


def handle_list(args):
    print_rows(RecordService(db_path()).list_all(), "关注池为空。")
    return 0


def handle_rm(args):
    removed = RecordService(db_path()).remove(args.code)
    print("已移除。" if removed else "关注池中没有这只股票。")
    return 0

