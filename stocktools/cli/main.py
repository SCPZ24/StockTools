from __future__ import annotations

import argparse
import sys

from . import cmd_alert, cmd_config, cmd_data, cmd_find, cmd_hold, cmd_record, cmd_watch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="st", description="StockTools A股中长线 CLI 工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    cmd_data.register(subparsers)
    cmd_config.register(subparsers)
    cmd_find.register(subparsers)
    cmd_record.register(subparsers)
    cmd_watch.register(subparsers)
    cmd_hold.register(subparsers)
    cmd_alert.register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("已取消。")
        return 130
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
