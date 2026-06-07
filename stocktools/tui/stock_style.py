from __future__ import annotations

from typing import Protocol

from rich.text import Text


class CloseDirectionRepo(Protocol):
    def get_latest_close_direction(self, code: str) -> str | None:
        ...


_DIRECTION_STYLES = {
    "up": "red",
    "down": "green",
    "flat": "white",
}


def stock_name_cell(repo: CloseDirectionRepo, code: str, name: str) -> Text:
    direction = repo.get_latest_close_direction(code)
    return Text(name, style=_DIRECTION_STYLES.get(direction, "white"))
