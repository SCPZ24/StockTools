from __future__ import annotations

from datetime import date
import math
import warnings

warnings.filterwarnings("ignore", message=r"urllib3 .* doesn't match a supported version!")
import requests

import pandas as pd


EASTMONEY_SPOT_URLS = [
    "https://82.push2.eastmoney.com/api/qt/clist/get",
    "https://push2.eastmoney.com/api/qt/clist/get",
    "https://40.push2.eastmoney.com/api/qt/clist/get",
]
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
EASTMONEY_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://quote.eastmoney.com/center/gridlist.html",
}


class AkshareProvider:
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
        last_error = None
        for url in EASTMONEY_SPOT_URLS:
            for trust_env in (True, False):
                session = requests.Session()
                session.trust_env = trust_env
                try:
                    return self._fetch_spot_records_from_url(session, url)
                except requests.RequestException as exc:
                    last_error = exc
                    continue
        if last_error is not None:
            raise RuntimeError(
                "Eastmoney 行情请求失败：已尝试系统环境代理、直连以及备用 host；"
                f"最后错误：{last_error}。请检查 HTTP_PROXY/HTTPS_PROXY 代理设置或当前网络是否能访问 push2.eastmoney.com。"
            ) from last_error
        return []

    def _fetch_spot_records_from_url(self, session: requests.Session, url: str) -> list[dict]:
        params = EASTMONEY_SPOT_PARAMS.copy()
        records = []
        page = 1
        total_pages = None
        while total_pages is None or page <= total_pages:
            params["pn"] = str(page)
            response = session.get(url, params=params, timeout=15, headers=EASTMONEY_HEADERS)
            response.raise_for_status()
            payload = response.json()
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
