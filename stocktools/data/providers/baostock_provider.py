from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


def to_bs_code(code: str) -> str:
    if code.startswith("6"):
        return f"sh.{code}"
    return f"sz.{code}"


def pure_code(code: str) -> str:
    return code.split(".")[-1]


class BaostockProvider:
    def __enter__(self):
        import baostock as bs

        self.bs = bs
        result = bs.login()
        if result.error_code != "0":
            raise RuntimeError(f"baostock 登录失败: {result.error_msg}")
        return self

    def __exit__(self, *exc):
        self.bs.logout()

    def list_stocks(self) -> list[dict]:
        day = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        data = self.bs.query_all_stock(day=day).get_data()
        stocks = []
        for _, row in data.iterrows():
            code = row["code"]
            name = row.get("code_name", "")
            if "ST" in str(name).upper():
                continue
            if not (code.startswith("sh.6") or code.startswith("sz.0") or code.startswith("sz.3")):
                continue
            stocks.append({"code": pure_code(code), "bs_code": code, "name": name})
        return stocks

    def fetch_history(self, code: str, start: str, end: str, name: str | None = None) -> list[dict]:
        bs_code = code if "." in code else to_bs_code(code)
        rs = self.bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume",
            start_date=start,
            end_date=end,
            frequency="d",
            adjustflag="2",
        )
        data = rs.get_data()
        if data is None or len(data) == 0:
            return []
        for col in ("open", "high", "low", "close", "volume"):
            data[col] = pd.to_numeric(data[col], errors="coerce")
        data = data.dropna()
        normalized = []
        for _, row in data.iterrows():
            normalized.append(
                {
                    "code": pure_code(bs_code),
                    "name": name or pure_code(bs_code),
                    "date": str(row["date"]),
                    "open": float(row["open"]),
                    "close": float(row["close"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "volume": float(row["volume"]),
                }
            )
        return normalized

