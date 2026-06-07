from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from stocktools.data.providers.akshare_provider import AkshareProvider
from stocktools.data.providers.baostock_provider import BaostockProvider
from stocktools.data.repos.kline_repo import KlineRepo


class DataService:
    def __init__(self, db_path: Path | str):
        self.kline_repo = KlineRepo(db_path)

    def init_history(self) -> dict:
        start = (date.today() - timedelta(days=365)).isoformat()
        end = date.today().isoformat()
        inserted = 0
        total = 0
        with BaostockProvider() as provider:
            for stock in provider.list_stocks():
                total += 1
                try:
                    rows = provider.fetch_history(stock["bs_code"], start, end, stock["name"])
                    inserted += self.kline_repo.bulk_insert(rows)
                except Exception:
                    continue
        return {"stocks": total, "rows": inserted}

    def update_daily(self) -> dict:
        trade_date = self._latest_possible_trade_date(date.today())
        trade_date_text = trade_date.isoformat()
        latest_date = self.kline_repo.get_latest_date()
        if latest_date and latest_date >= trade_date_text:
            return {"rows": 0, "date": latest_date, "status": "latest"}
        rows = AkshareProvider().fetch_daily_all(trade_date)
        inserted = self.kline_repo.bulk_insert(rows)
        return {"rows": inserted, "date": rows[0]["date"] if rows else trade_date_text, "status": "updated" if rows else "empty"}

    @staticmethod
    def _latest_possible_trade_date(today: date) -> date:
        if today.weekday() == 5:
            return today - timedelta(days=1)
        if today.weekday() == 6:
            return today - timedelta(days=2)
        return today
