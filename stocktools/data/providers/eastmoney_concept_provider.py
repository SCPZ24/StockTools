from __future__ import annotations

from .eastmoney_session import EASTMONEY_CLIST_URLS, EASTMONEY_KLINE_URLS, EastmoneySession


CONCEPT_LIST_PARAMS = {
    "pn": "1",
    "pz": "500",
    "po": "1",
    "np": "1",
    "fltt": "2",
    "invt": "2",
    "fid": "f3",
    "fs": "m:90 t:3 f:!50",
    "fields": "f12,f14,f2,f3,f6",
}

CONCEPT_KLINE_PARAMS = {
    "fields1": "f1,f2,f3,f4,f5,f6",
    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    "klt": "101",
    "fqt": "1",
}


def _num(value) -> float | None:
    try:
        if value in (None, "", "-", "--"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class EastmoneyConceptProvider:
    def __init__(self, session: EastmoneySession | None = None, kline_session: EastmoneySession | None = None):
        self.session = session or EastmoneySession(EASTMONEY_CLIST_URLS)
        self.kline_session = kline_session or session or EastmoneySession(EASTMONEY_KLINE_URLS)

    def fetch_concepts(self) -> list[dict]:
        payload = self.session.get_json(CONCEPT_LIST_PARAMS.copy())
        records = (payload.get("data") or {}).get("diff") or []
        concepts = []
        for row in records:
            code = str(row.get("f12") or "").strip()
            name = str(row.get("f14") or "").strip()
            price = _num(row.get("f2"))
            pct_chg = _num(row.get("f3"))
            amount = _num(row.get("f6")) or 0.0
            if not code.startswith("BK") or not name or price is None or pct_chg is None:
                continue
            concepts.append({"code": code, "name": name, "price": price, "pct_chg": pct_chg, "amount": amount})
        return concepts

    def fetch_kline(self, code: str, start: str, end: str) -> list[dict]:
        params = CONCEPT_KLINE_PARAMS.copy()
        params.update(
            {
                "secid": f"90.{code}",
                "beg": start.replace("-", ""),
                "end": end.replace("-", ""),
            }
        )
        payload = self.kline_session.get_json(params)
        lines = (payload.get("data") or {}).get("klines") or []
        rows = []
        for line in lines:
            parts = str(line).split(",")
            if len(parts) < 11:
                continue
            nums = [_num(parts[i]) for i in range(1, 11)]
            if any(v is None for v in nums):
                continue
            rows.append(
                {
                    "code": code,
                    "date": parts[0],
                    "open": float(nums[0]),
                    "close": float(nums[1]),
                    "high": float(nums[2]),
                    "low": float(nums[3]),
                    "volume": float(nums[4]),
                    "amount": float(nums[5]),
                    "pct_chg": float(nums[7]),
                    "turnover": float(nums[9]),
                }
            )
        return rows
