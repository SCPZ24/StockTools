from __future__ import annotations

import sqlite3
from pathlib import Path

from .schema import CONFIG_SCHEMA_SQL


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path | str) -> None:
    with connect(path) as conn:
        conn.executescript(CONFIG_SCHEMA_SQL)

