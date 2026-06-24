from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from stocktools.data.providers.eastmoney_concept_provider import EastmoneyConceptProvider
from stocktools.data.repos.concept_hotspot_repo import ConceptHotspotRepo
from stocktools.data.repos.concept_index_repo import ConceptIndexRepo
from stocktools.data.repos.concept_kline_repo import ConceptKlineRepo
from stocktools.scanners.ma_alignment import MAAlignmentScanner


_DEFAULT_PROVIDER = object()


class ConceptService:
    def __init__(self, db_path: Path | str, provider: EastmoneyConceptProvider | None | object = _DEFAULT_PROVIDER):
        self.db_path = db_path
        self.index_repo = ConceptIndexRepo(db_path)
        self.kline_repo = ConceptKlineRepo(db_path)
        self.hotspot_repo = ConceptHotspotRepo(db_path)
        self.provider = EastmoneyConceptProvider() if provider is _DEFAULT_PROVIDER else provider

    def sync_index(self) -> dict:
        if self.provider is None:
            return {"inserted": 0, "renamed": 0, "deactivated": 0}
        concepts = self.provider.fetch_concepts()
        return self.index_repo.sync(concepts)

    def init_history(self, start: str, end: str, on_progress=None) -> dict:
        if self.provider is None:
            return {"concepts": 0, "kline_rows": 0, "hotspot_rows": 0}
        concepts = self.provider.fetch_concepts()
        self.index_repo.sync(concepts)
        kline_rows = 0
        for idx, concept in enumerate(concepts, start=1):
            rows = self.provider.fetch_kline(concept["code"], start, end)
            kline_rows += self.kline_repo.bulk_upsert(rows)
            if on_progress is not None:
                on_progress(idx, len(concepts), concept["code"])
        hotspot_rows = self.hotspot_repo.replace_many(self.kline_repo.rebuild_daily_top10(start, end))
        return {"concepts": len(concepts), "kline_rows": kline_rows, "hotspot_rows": hotspot_rows}

    def update_daily(self, end: str) -> dict:
        if self.provider is None:
            return {"status": "skipped", "concepts": 0, "kline_rows": 0, "hotspot_rows": 0}
        concepts = self.provider.fetch_concepts()
        sync = self.index_repo.sync(concepts)
        latest = self.hotspot_repo.get_latest_date()
        if latest and latest >= end:
            return {"status": "latest", "sync": sync, "concepts": len(concepts), "kline_rows": 0, "hotspot_rows": 0}

        start = (
            (date.fromisoformat(latest) + timedelta(days=1)).isoformat()
            if latest
            else end
        )
        if start == end:
            hotspot_rows = self.hotspot_repo.replace_date(end, concepts)
            return {
                "status": "updated",
                "sync": sync,
                "concepts": len(concepts),
                "kline_rows": 0,
                "hotspot_rows": hotspot_rows,
            }

        kline_rows = 0
        for concept in self.index_repo.list_active():
            kline_rows += self.kline_repo.bulk_upsert(self.provider.fetch_kline(concept["code"], start, end))
        hotspot_rows = self.hotspot_repo.replace_many(self.kline_repo.rebuild_daily_top10(start, end))
        return {
            "status": "backfilled",
            "sync": sync,
            "concepts": len(concepts),
            "kline_rows": kline_rows,
            "hotspot_rows": hotspot_rows,
            "start": start,
        }

    def top(self, limit: int = 20, all_: bool = False) -> list[dict]:
        if self.provider is not None:
            try:
                concepts = self.provider.fetch_concepts()
                self.index_repo.sync(concepts)
                ranked = sorted(concepts, key=lambda r: (-float(r["pct_chg"]), r["code"]))
                rows = ranked if all_ else ranked[:limit]
                return [
                    {
                        "rank": idx + 1,
                        "code": row["code"],
                        "name": row["name"],
                        "price": row.get("price"),
                        "pct_chg": float(row["pct_chg"]),
                        "amount": float(row.get("amount") or 0),
                        "date": date.today().isoformat(),
                    }
                    for idx, row in enumerate(rows)
                ]
            except Exception:
                pass
        rows = self.hotspot_repo.get_latest_rows(None if all_ else limit)
        return [
            {
                "rank": row["rank"],
                "code": row["code"],
                "name": row.get("name") or row["code"],
                "price": row.get("price"),
                "pct_chg": float(row["pct_chg"]),
                "amount": float(row.get("amount") or 0),
                "date": row["date"],
            }
            for row in rows
        ]

    def hot(self) -> list[dict]:
        records = self.hotspot_repo.get_recent_records(10)
        if not records:
            return []
        dates = sorted({row["date"] for row in records})
        last3 = set(dates[-3:])
        by_code: dict[str, list[dict]] = {}
        for row in records:
            by_code.setdefault(row["code"], []).append(row)

        names = self.index_repo.names_by_code()
        result = []
        for code, rows in by_code.items():
            hit_dates = {row["date"] for row in rows}
            hit_7 = len(hit_dates) >= 7
            hit_3 = len(last3) == 3 and last3.issubset(hit_dates)
            if not (hit_7 or hit_3):
                continue
            self._lazy_refresh(code)
            cumulative = self._return_pct(code, 10)
            reasons = []
            if hit_7:
                reasons.append("10日7上榜")
            if hit_3:
                reasons.append("连续3天")
            result.append(
                {
                    "code": code,
                    "name": names.get(code, code),
                    "hit_7_of_10": hit_7,
                    "hit_3_consecutive": hit_3,
                    "reason": " + ".join(reasons),
                    "listed_days": len(hit_dates),
                    "consecutive_days": self._consecutive_days(dates, hit_dates),
                    "return_10d": cumulative,
                }
            )
        return sorted(result, key=lambda item: (-float(item["return_10d"]), item["code"]))

    def show(self, code: str) -> dict:
        info = self.index_repo.get(code)
        if info is None:
            raise ValueError(f"未知概念板块：{code}")
        self._lazy_refresh(code)
        rows = self.kline_repo.get_rows(code)
        latest = rows[-1] if rows else None
        hot_by_code = {item["code"]: item for item in self.hot()}
        hot = hot_by_code.get(code)
        return {
            "code": code,
            "name": info["name"],
            "latest": latest,
            "trend": self._trend(rows),
            "returns": {
                "ret_5d": self._return_pct_from_rows(rows, 5),
                "ret_10d": self._return_pct_from_rows(rows, 10),
                "ret_30d": self._return_pct_from_rows(rows, 30),
            },
            "hotspot": hot,
            "listing_bar": self._listing_bar(code),
        }

    def _lazy_refresh(self, code: str) -> None:
        if self.provider is None:
            return
        latest = self.kline_repo.get_latest_date(code)
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=180)).isoformat() if latest is None else (date.fromisoformat(latest) + timedelta(days=1)).isoformat()
        if latest and latest >= end:
            return
        rows = self.provider.fetch_kline(code, start, end)
        self.kline_repo.bulk_upsert(rows)

    def _trend(self, rows: list[dict]) -> str:
        if len(rows) < 120:
            return "数据不足"
        df = self.kline_repo.get_klines(rows[-1]["code"], 160)
        result = MAAlignmentScanner().detect(df)
        if result.matched:
            return "多头排列 (MA5>MA10>MA20>MA60)"
        closes = df["close"]
        ma5 = closes.rolling(5).mean().iloc[-1]
        ma10 = closes.rolling(10).mean().iloc[-1]
        ma20 = closes.rolling(20).mean().iloc[-1]
        ma60 = closes.rolling(60).mean().iloc[-1]
        latest = closes.iloc[-1]
        if latest > ma5 > ma10 > ma20 > ma60:
            return "多头排列 (MA5>MA10>MA20>MA60)"
        return "未形成多头排列"

    def _return_pct(self, code: str, days: int) -> float:
        rows = self.kline_repo.get_rows(code, days + 1)
        return self._return_pct_from_rows(rows, days)

    @staticmethod
    def _return_pct_from_rows(rows: list[dict], days: int) -> float:
        if len(rows) < days + 1:
            return 0.0
        start = float(rows[-days - 1]["close"])
        end = float(rows[-1]["close"])
        return round((end - start) / start * 100, 2) if start > 0 else 0.0

    @staticmethod
    def _consecutive_days(dates: list[str], hit_dates: set[str]) -> int:
        count = 0
        for day in reversed(dates):
            if day in hit_dates:
                count += 1
            else:
                break
        return count

    def _listing_bar(self, code: str) -> str:
        records = self.hotspot_repo.get_recent_records(10)
        dates = sorted({row["date"] for row in records})
        hit_dates = {row["date"] for row in records if row["code"] == code}
        return "".join("█" if day in hit_dates else "░" for day in dates)
