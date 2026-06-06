from __future__ import annotations

from pathlib import Path

from stocktools.ai.watch_analyst import WatchAnalyst
from stocktools.data.repos.ai_logs_repo import AiLogsRepo
from stocktools.data.repos.kline_repo import KlineRepo
from stocktools.data.repos.watchlist_repo import WatchlistRepo


class WatchService:
    def __init__(self, db_path: Path | str, analyst: WatchAnalyst | None = None):
        self.kline_repo = KlineRepo(db_path)
        self.watchlist_repo = WatchlistRepo(db_path)
        self.ai_logs_repo = AiLogsRepo(db_path)
        self.analyst = analyst or WatchAnalyst()

    def analyze(self, code: str | None = None):
        targets = [self.watchlist_repo.get(code)] if code else self.watchlist_repo.list_all()
        targets = [t for t in targets if t]
        results = []
        for item in targets:
            klines = self.kline_repo.get_klines(item["code"], 120)
            analysis = self.analyst.analyze(item["code"], item["name"], item.get("pattern"), klines)
            self.ai_logs_repo.upsert(item["code"], "watch", analysis.conclusion, analysis.content, analysis.analysis_date)
            results.append(analysis)
        return results

