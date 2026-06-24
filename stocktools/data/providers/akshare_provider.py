from __future__ import annotations

from datetime import date
import math

import pandas as pd

from .eastmoney_session import EASTMONEY_CLIST_URLS, EastmoneySession


EASTMONEY_SPOT_PARAMS = {
    "pn": "1",
    "pz": "100",
    "po": "1",
    "np": "1",
    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    "fltt": "2",
    "invt": "2",
    "fid": "f12",
    "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
    "fields": "f2,f5,f12,f14,f15,f16,f17",
}


class AkshareProvider:
    def __init__(self, session: EastmoneySession | None = None):
        self.session = session or EastmoneySession(EASTMONEY_CLIST_URLS)

    def fetch_daily_all(self, trade_date: date | None = None) -> list[dict]:
        rows = []
        row_date = (trade_date or date.today()).isoformat()
        for row in self._fetch_spot_records():
            code = str(row.get("f12", "")).zfill(6)
            if not (code.startswith("6") or code.startswith("0") or code.startswith("3")):
                continue
            name = str(row.get("f14", ""))
            if "ST" in name.upper():
                continue
            values = {
                "open": pd.to_numeric(row.get("f17"), errors="coerce"),
                "close": pd.to_numeric(row.get("f2"), errors="coerce"),
                "high": pd.to_numeric(row.get("f15"), errors="coerce"),
                "low": pd.to_numeric(row.get("f16"), errors="coerce"),
                "volume": pd.to_numeric(row.get("f5"), errors="coerce"),
            }
            if any(pd.isna(v) for v in values.values()):
                continue
            rows.append({"code": code, "name": name, "date": row_date, **{k: float(v) for k, v in values.items()}})
        return rows

    def _fetch_spot_records(self) -> list[dict]:
        params = EASTMONEY_SPOT_PARAMS.copy()
        records = []
        page = 1
        total_pages = None
        while total_pages is None or page <= total_pages:
            params["pn"] = str(page)
            payload = self.session.get_json(params)
            data = payload.get("data") or {}
            page_records = data.get("diff") or []
            if not page_records:
                break
            records.extend(page_records)
            total = int(data.get("total") or len(records))
            page_size = int(params["pz"])
            total_pages = min(math.ceil(total / page_size), 100)
            page += 1
        return records
