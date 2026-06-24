from __future__ import annotations

from stocktools.cli.common import db_path, valid_code
from stocktools.output.display import print_rows
from stocktools.services.alert_service import AlertService


def register(subparsers) -> None:
    parser = subparsers.add_parser("alert", help="执行卖出分析")
    parser.add_argument("code", nargs="?", type=valid_code)
    parser.set_defaults(func=handle)


def handle(args):
    service = AlertService(db_path())
    results = service.analyze(args.code, on_progress=_progress)
    rows = [r.__dict__ for r in results]
    print_rows(rows, "没有可分析的持仓。")
    for result in results:
        if result.suggested_stop_loss is not None or result.suggested_take_profit is not None:
            answer = input(f"{result.code} 是否写入建议止损/目标价？[y/n] ").strip().lower()
            if answer == "y":
                service.apply_suggestions(result.code, result.suggested_stop_loss, result.suggested_take_profit)
                print(f"{result.code} 已写入。")
    return 0


def _progress(event: dict) -> None:
    if event.get("type") == "sample":
        print(f"{event['code']} 第{event['round']}轮 {event['done']}/{event['total']} 路完成")
