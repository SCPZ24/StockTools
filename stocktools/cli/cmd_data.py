from __future__ import annotations

import argparse
from pathlib import Path

from stocktools.cli.common import db_path
from stocktools.infra.paths import Paths
from stocktools.services.cron_service import CronService
from stocktools.services.data_service import DataService


def register(subparsers) -> None:
    init = subparsers.add_parser("init", help="初始化历史行情")
    init.set_defaults(func=handle_init)
    update = subparsers.add_parser("update", help="更新当日行情")
    update.set_defaults(func=handle_update)
    cron = subparsers.add_parser("cron", help="管理自动更新")
    actions = cron.add_subparsers(dest="cron_cmd", required=True)
    set_cmd = actions.add_parser("set")
    set_cmd.add_argument("hh", type=int)
    set_cmd.add_argument("mm", type=int)
    set_cmd.set_defaults(func=handle_cron_set)
    remove_cmd = actions.add_parser("remove")
    remove_cmd.set_defaults(func=handle_cron_remove)


def handle_init(args: argparse.Namespace) -> int:
    result = DataService(db_path()).init_history()
    print(f"初始化完成：扫描 {result['stocks']} 只，写入 {result['rows']} 条。")
    return 0


def handle_update(args: argparse.Namespace) -> int:
    def notify_fallback() -> None:
        print("akshare 行情接口失败，回退到逐只抓取当前交易日（约 5000 次请求）：")

    result = DataService(db_path()).update_daily(on_fallback=notify_fallback)
    if result.get("status") == "latest":
        print(f"交易数据未更新，已是最新交易日 {result['date']}，写入 0 条。")
        return 0
    if result.get("status") == "fallback":
        print(f"回退更新完成：日期 {result['date']}，扫描 {result['stocks']} 只，写入 {result['rows']} 条。")
        return 0
    print(f"更新完成：日期 {result['date']}，写入 {result['rows']} 条。")
    return 0


def handle_cron_set(args: argparse.Namespace) -> int:
    st_path = Path.cwd() / "st.py"
    workdir = Paths.resolve().workdir
    command = f'STOCKTOOLS_HOME="{workdir}" python3 "{st_path}" update'
    CronService().set(args.hh, args.mm, command)
    print(f"已设置每日 {args.hh:02d}:{args.mm:02d} 自动更新。")
    return 0


def handle_cron_remove(args: argparse.Namespace) -> int:
    removed = CronService().remove()
    print("已移除 StockTools 自动更新 cron。" if removed else "没有找到 StockTools 自动更新 cron。")
    return 0
