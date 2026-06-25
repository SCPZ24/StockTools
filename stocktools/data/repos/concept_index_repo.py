from __future__ import annotations

from pathlib import Path

from stocktools.data.db import connect


class ConceptIndexRepo:
    def __init__(self, db_path: Path | str):
        self.db_path = db_path

    def sync(self, concepts: list[dict], deactivate_missing: bool = True) -> dict:
        incoming = {item["code"]: item["name"] for item in concepts}
        inserted = renamed = deactivated = 0
        with connect(self.db_path) as conn:
            existing = {
                row["code"]: dict(row)
                for row in conn.execute("SELECT code, name, active FROM concept_index").fetchall()
            }
            for code, name in incoming.items():
                old = existing.get(code)
                if old is None:
                    inserted += 1
                elif old["name"] != name:
                    renamed += 1
                conn.execute(
                    """
                    INSERT INTO concept_index(code, name, active)
                    VALUES (?, ?, 1)
                    ON CONFLICT(code) DO UPDATE SET
                        name=excluded.name,
                        active=1
                    """,
                    (code, name),
                )
            stale = [
                code
                for code, row in existing.items()
                if deactivate_missing and code not in incoming and int(row["active"]) == 1
            ]
            if stale:
                deactivated = len(stale)
                conn.executemany("UPDATE concept_index SET active = 0 WHERE code = ?", [(code,) for code in stale])
        return {"inserted": inserted, "renamed": renamed, "deactivated": deactivated}

    def get(self, code: str) -> dict | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT code, name, active FROM concept_index WHERE code = ?", (code,)).fetchone()
        return dict(row) if row else None

    def list_active(self) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT code, name, active FROM concept_index WHERE active = 1 ORDER BY code"
            ).fetchall()
        return [dict(row) for row in rows]

    def names_by_code(self) -> dict[str, str]:
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT code, name FROM concept_index").fetchall()
        return {row["code"]: row["name"] for row in rows}
