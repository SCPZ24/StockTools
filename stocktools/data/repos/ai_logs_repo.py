from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from stocktools.data.db import connect


class AiLogsRepo:
    def __init__(self, db_path: Path | str):
        self.db_path = db_path

    def insert(
        self,
        code: str,
        type_: str,
        conclusion: str,
        content: str,
        analysis_date: str | None = None,
        confidence: float | None = None,
        degraded: bool = False,
        votes: str | list[dict] | None = None,
    ) -> dict:
        day = analysis_date or date.today().isoformat()
        votes_text = json.dumps(votes, ensure_ascii=False) if isinstance(votes, list) else votes
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO ai_logs(code, type, conclusion, content, analysis_date, confidence, degraded, votes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (code, type_, conclusion, content, day, confidence, 1 if degraded else 0, votes_text),
            )
        return self.get_latest(code, type_)

    def upsert(
        self,
        code: str,
        type_: str,
        conclusion: str,
        content: str,
        analysis_date: str | None = None,
        confidence: float | None = None,
        degraded: bool = False,
        votes: str | list[dict] | None = None,
    ) -> dict:
        return self.insert(code, type_, conclusion, content, analysis_date, confidence, degraded, votes)

    def get_latest(self, code: str, type_: str) -> dict | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM ai_logs WHERE code = ? AND type = ? ORDER BY analysis_date DESC, created_at DESC, id DESC LIMIT 1",
                (code, type_),
            ).fetchone()
        return dict(row) if row else None

    def get_recent(self, code: str, type_: str, limit: int = 3) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM ai_logs WHERE code = ? AND type = ? ORDER BY analysis_date DESC, created_at DESC, id DESC LIMIT ?",
                (code, type_, limit),
            ).fetchall()
        return [dict(row) for row in rows]
