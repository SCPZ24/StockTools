from __future__ import annotations

from datetime import date
from pathlib import Path

from stocktools.data.db import connect


class AiLogsRepo:
    def __init__(self, db_path: Path | str):
        self.db_path = db_path

    def upsert(
        self,
        code: str,
        type_: str,
        conclusion: str,
        content: str,
        analysis_date: str | None = None,
    ) -> dict:
        day = analysis_date or date.today().isoformat()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO ai_logs(code, type, conclusion, content, analysis_date)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(code, type, analysis_date) DO UPDATE SET
                    conclusion=excluded.conclusion,
                    content=excluded.content,
                    created_at=datetime('now', 'localtime')
                """,
                (code, type_, conclusion, content, day),
            )
        return self.get_latest(code, type_)

    def get_latest(self, code: str, type_: str) -> dict | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM ai_logs WHERE code = ? AND type = ? ORDER BY analysis_date DESC, created_at DESC LIMIT 1",
                (code, type_),
            ).fetchone()
        return dict(row) if row else None

