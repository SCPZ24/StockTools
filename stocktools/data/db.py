from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

from .schema import MAIN_SCHEMA_SQL


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # 并发回退抓取时有多个写进程，让写入等待锁而不是立刻报 "database is locked"。
    conn.execute("PRAGMA busy_timeout=30000")
    # WAL 让多写进程不再抢全库写锁、读写互不阻塞；synchronous=NORMAL 在 WAL 下安全且更快。
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def connect_readonly(path: Path | str) -> sqlite3.Connection:
    db_path = Path(path).expanduser().resolve()
    uri = f"file://{quote(str(db_path))}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path | str) -> None:
    with connect(path) as conn:
        conn.executescript(MAIN_SCHEMA_SQL)
        _migrate_ai_logs(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_logs_code_type ON ai_logs(code, type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_logs_created ON ai_logs(created_at)")


def _migrate_ai_logs(conn: sqlite3.Connection) -> None:
    cols = [dict(row) for row in conn.execute("PRAGMA table_info(ai_logs)").fetchall()]
    if not cols:
        return
    col_names = {row["name"] for row in cols}
    has_required_cols = {"confidence", "degraded", "votes"}.issubset(col_names)
    has_legacy_unique = False
    for index in conn.execute("PRAGMA index_list(ai_logs)").fetchall():
        if not index["unique"]:
            continue
        indexed_cols = [row["name"] for row in conn.execute(f"PRAGMA index_info({index['name']})").fetchall()]
        if indexed_cols == ["code", "type", "analysis_date"]:
            has_legacy_unique = True
            break
    if has_required_cols and not has_legacy_unique:
        return

    conn.execute("DROP TABLE IF EXISTS ai_logs_new")
    conn.execute(
        """
        CREATE TABLE ai_logs_new (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT    NOT NULL,
            type        TEXT    NOT NULL,
            conclusion  TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            analysis_date TEXT  NOT NULL DEFAULT (date('now', 'localtime')),
            created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            confidence  REAL,
            degraded    INTEGER NOT NULL DEFAULT 0,
            votes       TEXT
        )
        """
    )
    select_cols = {
        "id": "id",
        "code": "code",
        "type": "type",
        "conclusion": "conclusion",
        "content": "content",
        "analysis_date": "analysis_date",
        "created_at": "created_at",
        "confidence": "confidence" if "confidence" in col_names else "NULL",
        "degraded": "degraded" if "degraded" in col_names else "0",
        "votes": "votes" if "votes" in col_names else "NULL",
    }
    conn.execute(
        f"""
        INSERT INTO ai_logs_new(id, code, type, conclusion, content, analysis_date, created_at, confidence, degraded, votes)
        SELECT {", ".join(select_cols[name] for name in select_cols)}
        FROM ai_logs
        ORDER BY id
        """
    )
    conn.execute("DROP TABLE ai_logs")
    conn.execute("ALTER TABLE ai_logs_new RENAME TO ai_logs")


@contextmanager
def transaction(path: Path | str) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
