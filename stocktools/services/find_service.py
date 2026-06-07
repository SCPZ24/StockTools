from __future__ import annotations

import statistics
from pathlib import Path
from typing import Iterator

from stocktools.data.repos.kline_repo import KlineRepo
from stocktools.scanners.registry import get_scanner


class FindService:
    def __init__(self, db_path: Path | str):
        self.kline_repo = KlineRepo(db_path)

    def _baseline_return(self) -> float:
        returns = []
        for stock in self.kline_repo.list_codes():
            df = self.kline_repo.get_klines(stock["code"], 70)
            if len(df) >= 60:
                start = float(df.tail(60).iloc[0]["close"])
                end = float(df.iloc[-1]["close"])
                if start > 0:
                    returns.append(end / start - 1)
        return statistics.median(returns) if returns else 0.0

    def iter_scan(self, scanner_name: str, options: dict | None = None) -> Iterator[dict]:
        options = dict(options or {})
        if scanner_name == "independent" and "baseline_return" not in options:
            options["baseline_return"] = self._baseline_return()
        scanner = get_scanner(scanner_name)
        for stock in self.kline_repo.list_codes():
            df = self.kline_repo.get_klines(stock["code"])
            result = scanner.detect(df, **options)
            if result.matched:
                yield {"code": stock["code"], "name": stock["name"], "pattern": result.pattern, **result.indicators}

    def scan(self, scanner_name: str, options: dict | None = None) -> list[dict]:
        return list(self.iter_scan(scanner_name, options))
