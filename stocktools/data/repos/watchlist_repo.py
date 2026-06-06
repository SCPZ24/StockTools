from __future__ import annotations

from pathlib import Path

from stocktools.data.db import connect


class WatchlistRepo:
    def __init__(self, db_path: Path | str):
        self.db_path = db_path

    def add(self, code: str, name: str, pattern: str | None = None, note: str | None = None) -> dict:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO watchlist(code, name, pattern, note)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name,
                    pattern=excluded.pattern,
                    note=COALESCE(excluded.note, watchlist.note)
                """,
                (code, name, pattern, note),
            )
        return self.get(code)

    def get(self, code: str) -> dict | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM watchlist WHERE code = ?", (code,)).fetchone()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM watchlist ORDER BY added_at DESC, code").fetchall()
        return [dict(row) for row in rows]

    def remove(self, code: str) -> bool:
        with connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM watchlist WHERE code = ?", (code,))
        return cur.rowcount > 0

    def update_note(self, code: str, message: str, replace: bool = False) -> dict:
        current = self.get(code)
        if current is None:
            raise ValueError(f"关注池中没有 {code}")
        note = message if replace or not current.get("note") else f"{current['note']}\n{message}"
        with connect(self.db_path) as conn:
            conn.execute("UPDATE watchlist SET note = ? WHERE code = ?", (note, code))
        return self.get(code)

    def set_buy_tomorrow(self, code: str, value: bool = True) -> dict:
        if self.get(code) is None:
            raise ValueError(f"关注池中没有 {code}")
        with connect(self.db_path) as conn:
            conn.execute("UPDATE watchlist SET buy_tomorrow = ? WHERE code = ?", (1 if value else 0, code))
        return self.get(code)

    def update_pattern(self, code: str, pattern: str | None) -> dict:
        with connect(self.db_path) as conn:
            conn.execute("UPDATE watchlist SET pattern = ? WHERE code = ?", (pattern, code))
        return self.get(code)

