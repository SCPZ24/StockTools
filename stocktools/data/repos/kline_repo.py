from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Callable, TypeVar

import pandas as pd

from stocktools.data.db import connect, connect_readonly

T = TypeVar("T")


class KlineRepo:
    def __init__(self, db_path: Path | str):
        self.db_path = db_path

    def _read(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        conn = connect(self.db_path)
        try:
            result = operation(conn)
        except (sqlite3.OperationalError, pd.errors.DatabaseError) as exc:
            conn.close()
            if "unable to open database file" not in str(exc):
                raise
            conn2 = connect_readonly(self.db_path)
            try:
                return operation(conn2)
            finally:
                conn2.close()
        else:
            return result
        finally:
            conn.close()

    def bulk_insert(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        values = [
            (
                r["code"],
                r["name"],
                r["date"],
                float(r["open"]),
                float(r["close"]),
                float(r["high"]),
                float(r["low"]),
                float(r["volume"]),
            )
            for r in rows
        ]
        with connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO daily_kline(code, name, date, open, close, high, low, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, date) DO UPDATE SET
                    name=excluded.name,
                    open=excluded.open,
                    close=excluded.close,
                    high=excluded.high,
                    low=excluded.low,
                    volume=excluded.volume
                """,
                values,
            )
        return len(values)

    def get_klines(self, code: str, n_days: int | None = None) -> pd.DataFrame:
        limit = "" if n_days is None else f"LIMIT {int(n_days)}"
        query = f"""
            SELECT code, name, date, open, close, high, low, volume
            FROM daily_kline
            WHERE code = ?
            ORDER BY date DESC
            {limit}
        """
        df = self._read(lambda conn: pd.read_sql_query(query, conn, params=(code,)))
        if df.empty:
            return df
        return df.sort_values("date").reset_index(drop=True)

    # Tradable A-share equity code prefixes (excludes indices like 399xxx).
    STOCK_PREFIXES = ("000", "001", "002", "003", "300", "301", "302", "600", "601", "603", "605", "688", "689")

    def list_codes(self) -> list[dict]:
        placeholders = ",".join("?" for _ in self.STOCK_PREFIXES)
        rows = self._read(
            lambda conn: conn.execute(
                f"""
                SELECT k.code, k.name
                FROM daily_kline k
                JOIN (
                    SELECT code, max(date) AS latest_date
                    FROM daily_kline
                    GROUP BY code
                ) latest ON latest.code = k.code AND latest.latest_date = k.date
                WHERE substr(k.code, 1, 3) IN ({placeholders})
                  AND k.name NOT LIKE '%退%'
                  AND k.name NOT LIKE '%指数%'
                ORDER BY k.code
                """,
                self.STOCK_PREFIXES,
            ).fetchall()
        )
        return [dict(row) for row in rows]

    def get_latest_date(self) -> str | None:
        row = self._read(lambda conn: conn.execute("SELECT max(date) AS latest_date FROM daily_kline").fetchone())
        return row["latest_date"] if row else None

    def get_latest_name(self, code: str) -> str | None:
        row = self._read(
            lambda conn: conn.execute(
                "SELECT name FROM daily_kline WHERE code = ? ORDER BY date DESC LIMIT 1",
                (code,),
            ).fetchone()
        )
        return row["name"] if row else None
