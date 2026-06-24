from __future__ import annotations

from stocktools.cli.common import db_path, valid_code
from stocktools.output.display import print_rows
from stocktools.services.watch_service import WatchService


def register(subparsers) -> None:
    parser = subparsers.add_parser("watch", help="执行买入分析")
    parser.add_argument("code", nargs="?", type=valid_code)
    parser.set_defaults(func=handle)


def handle(args):
    rows = [r.__dict__ for r in WatchService(db_path()).analyze(args.code, on_progress=_progress)]
    print_rows(rows, "没有可分析的关注股票。")
    return 0


def _progress(event: dict) -> None:
    if event.get("type") == "sample":
        print(f"{event['code']} 第{event['round']}轮 {event['done']}/{event['total']} 路完成")
