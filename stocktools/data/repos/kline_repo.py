from __future__ import annotations

from pathlib import Path

import pandas as pd

from stocktools.data.db import connect


class KlineRepo:
    def __init__(self, db_path: Path | str):
        self.db_path = db_path

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
        with connect(self.db_path) as conn:
            df = pd.read_sql_query(query, conn, params=(code,))
        if df.empty:
            return df
        return df.sort_values("date").reset_index(drop=True)

    def list_codes(self) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT k.code, k.name
                FROM daily_kline k
                JOIN (
                    SELECT code, max(date) AS latest_date
                    FROM daily_kline
                    GROUP BY code
                ) latest ON latest.code = k.code AND latest.latest_date = k.date
                ORDER BY k.code
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_latest_date(self) -> str | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT max(date) AS latest_date FROM daily_kline").fetchone()
        return row["latest_date"] if row else None

    def get_latest_name(self, code: str) -> str | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT name FROM daily_kline WHERE code = ? ORDER BY date DESC LIMIT 1",
                (code,),
            ).fetchone()
        return row["name"] if row else None

