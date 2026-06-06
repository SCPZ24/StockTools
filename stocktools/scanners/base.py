from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from .results import ScanResult


class BaseScanner(ABC):
    name: str
    label: str

    @abstractmethod
    def detect(self, df: pd.DataFrame, **kwargs) -> ScanResult:
        raise NotImplementedError

