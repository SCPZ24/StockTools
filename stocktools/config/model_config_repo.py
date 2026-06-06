from __future__ import annotations

from pathlib import Path

from stocktools.config.db import connect


class ModelConfigRepo:
    def __init__(self, db_path: Path | str):
        self.db_path = db_path

    def upsert(self, base_url: str, api_key: str, model_name: str) -> dict:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO model_config(id, base_url, api_key, model_name)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    base_url=excluded.base_url,
                    api_key=excluded.api_key,
                    model_name=excluded.model_name
                """,
                (base_url, api_key, model_name),
            )
        return self.get()

    def get(self) -> dict | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM model_config WHERE id = 1").fetchone()
        return dict(row) if row else None

