from __future__ import annotations

from datetime import date
from pathlib import Path

from stocktools.data.db import connect


class HoldingsRepo:
    def __init__(self, db_path: Path | str):
        self.db_path = db_path

    def add_entry(
        self,
        code: str,
        name: str,
        entry_price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        note: str | None = None,
    ) -> dict:
        with connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO holdings(code, name, entry_price, stop_loss, take_profit, note)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (code, name, entry_price, stop_loss, take_profit, note),
            )
            row_id = cur.lastrowid
        return self.get(row_id)

    def get(self, holding_id: int) -> dict:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM holdings WHERE id = ?", (holding_id,)).fetchone()
        return dict(row)

    def list_open(self, code: str | None = None) -> list[dict]:
        where = "WHERE status = 'open'"
        params: tuple = ()
        if code:
            where += " AND code = ?"
            params = (code,)
        with connect(self.db_path) as conn:
            rows = conn.execute(f"SELECT * FROM holdings {where} ORDER BY entry_date DESC, id DESC", params).fetchall()
        return [dict(row) for row in rows]

    def list_closed(self, near: int | None = None) -> list[dict]:
        limit = "" if near is None else f" LIMIT {int(near)}"
        with connect(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM holdings WHERE status = 'closed' ORDER BY exit_date DESC, id DESC{limit}"
            ).fetchall()
        return [dict(row) for row in rows]

    def close_all_open_by_code(self, code: str, exit_price: float) -> int:
        with connect(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE holdings
                SET status = 'closed', exit_price = ?, exit_date = ?
                WHERE code = ? AND status = 'open'
                """,
                (exit_price, date.today().isoformat(), code),
            )
        return cur.rowcount

    def append_reduction_note(self, code: str, price: float) -> int:
        note = f"{date.today().isoformat()} 减仓，价格 {price}"
        with connect(self.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE holdings
                SET note = CASE WHEN note IS NULL OR note = '' THEN ? ELSE note || char(10) || ? END
                WHERE code = ? AND status = 'open'
                """,
                (note, note, code),
            )
        return cur.rowcount

    def update_stop_loss(self, code: str, stop_loss: float) -> int:
        with connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE holdings SET stop_loss = ? WHERE code = ? AND status = 'open'",
                (stop_loss, code),
            )
        return cur.rowcount

    def update_take_profit(self, code: str, take_profit: float) -> int:
        with connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE holdings SET take_profit = ? WHERE code = ? AND status = 'open'",
                (take_profit, code),
            )
        return cur.rowcount

    def update_note(self, code: str, note: str) -> int:
        with connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE holdings SET note = ? WHERE code = ? AND status = 'open'",
                (note, code),
            )
        return cur.rowcount

