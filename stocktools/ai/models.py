from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WatchAnalysis:
    code: str
    conclusion: str
    content: str
    analysis_date: str
    confidence: float | None = None
    degraded: bool = False
    votes: str | None = None


@dataclass
class AlertAnalysis:
    code: str
    conclusion: str
    content: str
    analysis_date: str
    suggested_stop_loss: float | None = None
    suggested_take_profit: float | None = None
    confidence: float | None = None
    degraded: bool = False
    votes: str | None = None
