from __future__ import annotations

from pathlib import Path
from typing import Iterator

from stocktools.data.repos.kline_repo import KlineRepo
from stocktools.scanners.registry import get_scanner


class FindService:
    def __init__(self, db_path: Path | str):
        self.kline_repo = KlineRepo(db_path)

    def iter_scan(self, scanner_name: str, options: dict | None = None) -> Iterator[dict]:
        options = dict(options or {})
        scanner = get_scanner(scanner_name)
        for stock in self.kline_repo.list_codes():
            df = self.kline_repo.get_klines(stock["code"])
            result = scanner.detect(df, **options)
            if result.matched:
                yield {"code": stock["code"], "name": stock["name"], "pattern": result.pattern, **result.indicators}

    def scan(self, scanner_name: str, options: dict | None = None, limit: int | None = None) -> list[dict]:
        rows = list(self.iter_scan(scanner_name, options))
        rows.sort(key=lambda r: float(r.get("score", 0)), reverse=True)
        return rows[:limit] if limit else rows
