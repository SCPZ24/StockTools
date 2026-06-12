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
