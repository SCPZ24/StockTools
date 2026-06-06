from __future__ import annotations

from pathlib import Path

from stocktools.data.repos.holdings_repo import HoldingsRepo
from stocktools.data.repos.kline_repo import KlineRepo


class HoldService:
    def __init__(self, db_path: Path | str):
        self.kline_repo = KlineRepo(db_path)
        self.holdings_repo = HoldingsRepo(db_path)

    def add_entry(self, code: str, price: float, stop: float | None = None, target: float | None = None, note: str | None = None) -> dict:
        name = self.kline_repo.get_latest_name(code) or code
        return self.holdings_repo.add_entry(code, name, price, stop, target, note)

    def exit(self, code: str, price: float, decrease: bool = False) -> int:
        if decrease:
            return self.holdings_repo.append_reduction_note(code, price)
        return self.holdings_repo.close_all_open_by_code(code, price)

    def set_fields(self, code: str, stop: float | None = None, target: float | None = None, note: str | None = None) -> int:
        count = 0
        if stop is not None:
            count = max(count, self.holdings_repo.update_stop_loss(code, stop))
        if target is not None:
            count = max(count, self.holdings_repo.update_take_profit(code, target))
        if note is not None:
            count = max(count, self.holdings_repo.update_note(code, note))
        return count

    def show(self, code: str) -> list[dict]:
        return self.holdings_repo.list_open(code)

    def list_open(self) -> list[dict]:
        return self.holdings_repo.list_open()

    def history(self, near: int | None = None) -> list[dict]:
        return self.holdings_repo.list_closed(near)

