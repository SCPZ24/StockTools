from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from stocktools.config.db import init_db as init_config_db
from stocktools.data.db import init_db as init_main_db


@dataclass(frozen=True)
class Paths:
    workdir: Path

    @property
    def database_path(self) -> Path:
        return self.workdir / "database.db"

    @property
    def config_path(self) -> Path:
        return self.workdir / "config.db"

    @classmethod
    def resolve(cls) -> "Paths":
        env_home = os.environ.get("STOCKTOOLS_HOME")
        if env_home:
            return cls(Path(env_home).expanduser())
        marker = Path.home() / ".stock_tools_path"
        if marker.exists():
            content = marker.read_text(encoding="utf-8").strip()
            if content:
                return cls(Path(content).expanduser())
        return cls(Path.home() / ".stock_tools")

    def ensure_workdir(self) -> None:
        self.workdir.mkdir(parents=True, exist_ok=True)

    def init_databases(self) -> None:
        self.ensure_workdir()
        init_main_db(self.database_path)
        init_config_db(self.config_path)

