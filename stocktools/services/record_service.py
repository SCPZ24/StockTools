from __future__ import annotations

from pathlib import Path

from stocktools.data.repos.kline_repo import KlineRepo
from stocktools.data.repos.watchlist_repo import WatchlistRepo
from stocktools.scanners.registry import scanner_names, get_scanner


class RecordService:
    def __init__(self, db_path: Path | str):
        self.kline_repo = KlineRepo(db_path)
        self.watchlist_repo = WatchlistRepo(db_path)

    def add(self, code: str, note: str | None = None) -> dict:
        name = self.kline_repo.get_latest_name(code)
        if not name:
            raise ValueError(f"本地行情中找不到 {code}，请先运行 st init 或 st update")
        df = self.kline_repo.get_klines(code)
        patterns = []
        for scanner_name in scanner_names():
            try:
                result = get_scanner(scanner_name).detect(df)
            except Exception:
                result = None
            if result and result.matched:
                patterns.append(scanner_name)
        return self.watchlist_repo.add(code, name, ",".join(patterns) if patterns else None, note)

    def show(self, code: str) -> dict | None:
        return self.watchlist_repo.get(code)

    def note(self, code: str, message: str, replace: bool = False) -> dict:
        return self.watchlist_repo.update_note(code, message, replace)

    def go(self, code: str) -> dict:
        return self.watchlist_repo.set_buy_tomorrow(code, True)

    def list_all(self) -> list[dict]:
        return self.watchlist_repo.list_all()

    def remove(self, code: str) -> bool:
        return self.watchlist_repo.remove(code)

