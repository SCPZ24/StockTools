"""股票池管理 — 沪深300 / 中证500 / 中证800 / 全A"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .provider_baostock import BaostockSession


def load_stock_list(session: "BaostockSession", pool: str = "csi800") -> list[dict]:
    all_data = session.query_all_stocks()

    stocks = []
    for _, row in all_data.iterrows():
        code = row["code"]
        name = row["code_name"]
        if "ST" in name.upper():
            continue
        if not (code.startswith("sh.6") or code.startswith("sz.0") or code.startswith("sz.3")):
            continue
        stocks.append({"code": code, "name": name})

    if pool == "all":
        print(f"  全A股: {len(stocks)}只")
        return stocks

    valid: set[str] = set()
    if pool in ("csi300", "csi800"):
        codes = session.query_hs300()
        valid |= codes
        print(f"  沪深300: {len(codes)}只")

    if pool in ("csi500", "csi800"):
        codes = session.query_zz500()
        valid |= codes
        print(f"  中证500: {len(codes)}只")

    if valid:
        stocks = [s for s in stocks if s["code"] in valid]

    print(f"  有效股票: {len(stocks)}只")
    return stocks
