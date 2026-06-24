from __future__ import annotations

from pathlib import Path

from stocktools.data.db import connect


class ConceptHotspotRepo:
    def __init__(self, db_path: Path | str):
        self.db_path = db_path

    def replace_date(self, day: str, rows: list[dict]) -> int:
        ranked = sorted(rows, key=lambda r: (-float(r["pct_chg"]), r["code"]))[:10]
        values = [(day, row["code"], idx + 1, float(row["pct_chg"])) for idx, row in enumerate(ranked)]
        with connect(self.db_path) as conn:
            conn.execute("DELETE FROM daily_hotspot WHERE date = ?", (day,))
            conn.executemany(
                "INSERT INTO daily_hotspot(date, code, rank, pct_chg) VALUES (?, ?, ?, ?)",
                values,
            )
        return len(values)

    def replace_many(self, grouped: dict[str, list[dict]]) -> int:
        count = 0
        for day, rows in grouped.items():
            count += self.replace_date(day, rows)
        return count

    def get_latest_date(self) -> str | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT max(date) AS latest_date FROM daily_hotspot").fetchone()
        return row["latest_date"] if row else None

    def get_recent_records(self, n_dates: int = 10) -> list[dict]:
        with connect(self.db_path) as conn:
            dates = [
                row["date"]
                for row in conn.execute(
                    "SELECT DISTINCT date FROM daily_hotspot ORDER BY date DESC LIMIT ?",
                    (n_dates,),
                ).fetchall()
            ]
            if not dates:
                return []
            placeholders = ",".join("?" for _ in dates)
            rows = conn.execute(
                f"""
                SELECT h.date, h.code, h.rank, h.pct_chg, i.name
                FROM daily_hotspot h
                LEFT JOIN concept_index i ON i.code = h.code
                WHERE h.date IN ({placeholders})
                ORDER BY h.date DESC, h.rank
                """,
                dates,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_latest_rows(self, limit: int | None = None) -> list[dict]:
        latest = self.get_latest_date()
        if latest is None:
            return []
        limit_sql = "" if limit is None else f"LIMIT {int(limit)}"
        with connect(self.db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT h.date, h.code, h.rank, h.pct_chg, i.name,
                       k.close AS price, k.amount AS amount
                FROM daily_hotspot h
                LEFT JOIN concept_index i ON i.code = h.code
                LEFT JOIN concept_kline k ON k.code = h.code AND k.date = h.date
                WHERE h.date = ?
                ORDER BY h.rank
                {limit_sql}
                """,
                (latest,),
            ).fetchall()
        return [dict(row) for row in rows]
