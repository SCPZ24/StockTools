from __future__ import annotations

from datetime import date

import pandas as pd


class AkshareProvider:
    def fetch_daily_all(self, trade_date: date | None = None) -> list[dict]:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("缺少 akshare 依赖，请先安装 requirements.txt") from exc
        df = ak.stock_zh_a_spot_em()
        columns = {
            "代码": "code",
            "名称": "name",
            "今开": "open",
            "最新价": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
        }
        missing = [c for c in columns if c not in df.columns]
        if missing:
            raise RuntimeError(f"akshare 返回字段缺失: {', '.join(missing)}")
        rows = []
        row_date = (trade_date or date.today()).isoformat()
        for _, row in df.iterrows():
            code = str(row["代码"]).zfill(6)
            if not (code.startswith("6") or code.startswith("0") or code.startswith("3")):
                continue
            name = str(row["名称"])
            if "ST" in name.upper():
                continue
            values = {target: pd.to_numeric(row[source], errors="coerce") for source, target in columns.items() if target not in ("code", "name")}
            if any(pd.isna(v) for v in values.values()):
                continue
            rows.append({"code": code, "name": name, "date": row_date, **{k: float(v) for k, v in values.items()}})
        return rows
