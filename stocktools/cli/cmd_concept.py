from __future__ import annotations

import argparse
import re
import sys

from stocktools.cli.common import db_path
from stocktools.services.concept_service import ConceptService


def valid_concept_code(value: str) -> str:
    code = value.upper()
    if not re.fullmatch(r"BK\d+", code):
        raise argparse.ArgumentTypeError("概念代码必须形如 BK1128")
    return code


def register(subparsers) -> None:
    parser = subparsers.add_parser("concept", help="概念板块热点监控")
    actions = parser.add_subparsers(dest="concept_cmd", required=True)

    top = actions.add_parser("top", help="查看概念涨幅榜")
    top.add_argument("-n", "--limit", type=int, default=20, help="显示前 N 个，默认 20")
    top.add_argument("--all", action="store_true", help="显示全部概念板块")
    top.set_defaults(func=handle_top)

    hot = actions.add_parser("hot", help="查看当前短期小热点")
    hot.set_defaults(func=handle_hot)

    show = actions.add_parser("show", help="查看单个概念板块详情")
    show.add_argument("code", type=valid_concept_code)
    show.set_defaults(func=handle_show)


def handle_top(args: argparse.Namespace) -> int:
    rows = ConceptService(db_path()).top(limit=args.limit, all_=args.all)
    if not rows:
        print("没有概念涨幅榜数据。")
        return 0
    print(f"日期: {rows[0].get('date', '-')}")
    printable = [
        {
            "排名": row["rank"],
            "代码": row["code"],
            "名称": row["name"],
            "涨幅": _pct(row["pct_chg"]),
            "成交额(亿)": _yi(row["amount"]),
        }
        for row in rows
    ]
    _print_table(printable, paginate=args.all and sys.stdout.isatty())
    return 0


def handle_hot(args: argparse.Namespace) -> int:
    rows = ConceptService(db_path()).hot()
    if not rows:
        print("当前没有短期小热点。")
        return 0
    print("当前短期小热点:")
    printable = [
        {
            "代码": row["code"],
            "名称": row["name"],
            "条件": row["reason"],
            "上榜": f"{row['listed_days']}/10天",
            "连续": f"{row['consecutive_days']}天",
            "累计": _pct(row["return_10d"]),
        }
        for row in rows
    ]
    _print_table(printable)
    return 0


def handle_show(args: argparse.Namespace) -> int:
    detail = ConceptService(db_path()).show(args.code)
    latest = detail.get("latest") or {}
    hotspot = detail.get("hotspot")
    print(f"{detail['name']} ({detail['code']})")
    print(f"最新价: {latest.get('close', '-')}" + (f" ({_pct(latest.get('pct_chg', 0))})" if latest else ""))
    print(f"成交额: {_yi(latest.get('amount', 0))}亿")
    print(f"趋势(日线): {detail['trend']}")
    print(f"近5日涨幅: {_pct(detail['returns']['ret_5d'])}")
    print(f"近10日涨幅: {_pct(detail['returns']['ret_10d'])}")
    print(f"近30日涨幅: {_pct(detail['returns']['ret_30d'])}")
    if hotspot:
        print(f"热点状态: 短期小热点 ({hotspot['reason']})")
    else:
        print("热点状态: 否")
    print(f"近10日上榜记录: {detail['listing_bar']}")
    return 0


def _pct(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.2f}%"


def _yi(value) -> str:
    try:
        return f"{float(value) / 100000000:.1f}"
    except (TypeError, ValueError):
        return "-"


def _print_table(rows: list[dict], paginate: bool = False) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    widths = {key: max(len(str(key)), *(len(str(row.get(key, ""))) for row in rows)) for key in keys}
    for start in range(0, len(rows), 20):
        chunk = rows[start : start + 20]
        if start:
            print()
        print("  ".join(str(key).ljust(widths[key]) for key in keys))
        print("  ".join("-" * widths[key] for key in keys))
        for row in chunk:
            print("  ".join(str(row.get(key, "")).ljust(widths[key]) for key in keys))
        if paginate and start + 20 < len(rows):
            input("按 Enter 继续...")
