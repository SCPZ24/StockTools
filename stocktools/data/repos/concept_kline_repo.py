from __future__ import annotations

from pathlib import Path

from stocktools.data.db import connect


class ConceptKlineRepo:
    def __init__(self, db_path: Path | str):
        self.db_path = db_path

    def bulk_upsert(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        values = [
            (
                r["code"],
                r["date"],
                float(r["open"]),
                float(r["close"]),
                float(r["high"]),
                float(r["low"]),
                float(r["volume"]),
                float(r["amount"]),
                float(r["pct_chg"]),
                float(r["turnover"]),
            )
            for r in rows
        ]
        with connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO concept_kline(code, date, open, close, high, low, volume, amount, pct_chg, turnover)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, date) DO UPDATE SET
                    open=excluded.open,
                    close=excluded.close,
                    high=excluded.high,
                    low=excluded.low,
                    volume=excluded.volume,
                    amount=excluded.amount,
                    pct_chg=excluded.pct_chg,
                    turnover=excluded.turnover
                """,
                values,
            )
        return len(values)

    def get_rows(self, code: str, n_days: int | None = None) -> list[dict]:
        limit = "" if n_days is None else f"LIMIT {int(n_days)}"
        query = f"""
            SELECT code, date, open, close, high, low, volume, amount, pct_chg, turnover
            FROM concept_kline
            WHERE code = ?
            ORDER BY date DESC
            {limit}
        """
        with connect(self.db_path) as conn:
            rows = conn.execute(query, (code,)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def get_klines(self, code: str, n_days: int | None = None):
        import pandas as pd

        columns = ["code", "date", "open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover"]
        return pd.DataFrame(self.get_rows(code, n_days), columns=columns)

    def get_latest_date(self, code: str | None = None) -> str | None:
        with connect(self.db_path) as conn:
            if code:
                row = conn.execute("SELECT max(date) AS latest_date FROM concept_kline WHERE code = ?", (code,)).fetchone()
            else:
                row = conn.execute("SELECT max(date) AS latest_date FROM concept_kline").fetchone()
        return row["latest_date"] if row else None

    def get_latest_row(self, code: str) -> dict | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT code, date, open, close, high, low, volume, amount, pct_chg, turnover
                FROM concept_kline
                WHERE code = ?
                ORDER BY date DESC
                LIMIT 1
                """,
                (code,),
            ).fetchone()
        return dict(row) if row else None

    def rebuild_daily_top10(self, start: str | None = None, end: str | None = None) -> dict[str, list[dict]]:
        filters = []
        params: list[str] = []
        if start:
            filters.append("date >= ?")
            params.append(start)
        if end:
            filters.append("date <= ?")
            params.append(end)
        where = "" if not filters else "WHERE " + " AND ".join(filters)
        with connect(self.db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT code, date, pct_chg
                FROM concept_kline
                {where}
                ORDER BY date, pct_chg DESC, code
                """,
                params,
            ).fetchall()
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row["date"], []).append({"code": row["code"], "pct_chg": float(row["pct_chg"])})
        return {day: items[:10] for day, items in grouped.items()}
