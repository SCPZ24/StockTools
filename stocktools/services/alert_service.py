from __future__ import annotations

from pathlib import Path

from stocktools.ai.alert_analyst import AlertAnalyst
from stocktools.data.repos.ai_logs_repo import AiLogsRepo
from stocktools.data.repos.holdings_repo import HoldingsRepo
from stocktools.data.repos.kline_repo import KlineRepo


class AlertService:
    def __init__(self, db_path: Path | str, analyst: AlertAnalyst | None = None):
        self.kline_repo = KlineRepo(db_path)
        self.holdings_repo = HoldingsRepo(db_path)
        self.ai_logs_repo = AiLogsRepo(db_path)
        self.analyst = analyst or AlertAnalyst()

    def analyze(self, code: str | None = None):
        holdings = self.holdings_repo.list_open(code)
        results = []
        for holding in holdings:
            klines = self.kline_repo.get_klines(holding["code"], 120)
            analysis = self.analyst.analyze(holding, klines)
            self.ai_logs_repo.upsert(holding["code"], "alert", analysis.conclusion, analysis.content, analysis.analysis_date)
            results.append(analysis)
        return results

    def apply_suggestions(self, code: str, stop_loss: float | None = None, take_profit: float | None = None) -> int:
        count = 0
        if stop_loss is not None:
            count = max(count, self.holdings_repo.update_stop_loss(code, stop_loss))
        if take_profit is not None:
            count = max(count, self.holdings_repo.update_take_profit(code, take_profit))
        return count

