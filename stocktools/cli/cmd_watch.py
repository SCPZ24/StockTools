from __future__ import annotations

from stocktools.cli.common import db_path, valid_code
from stocktools.output.display import print_rows
from stocktools.services.watch_service import WatchService


def register(subparsers) -> None:
    parser = subparsers.add_parser("watch", help="执行买入分析")
    parser.add_argument("code", nargs="?", type=valid_code)
    parser.set_defaults(func=handle)


def handle(args):
    rows = [r.__dict__ for r in WatchService(db_path()).analyze(args.code)]
    print_rows(rows, "没有可分析的关注股票。")
    return 0

