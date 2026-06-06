from __future__ import annotations

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    @abstractmethod
    def fetch_history(self, code: str, start: str, end: str) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def fetch_daily_all(self) -> list[dict]:
        raise NotImplementedError

