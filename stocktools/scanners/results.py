from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScanResult:
    matched: bool
    pattern: str
    indicators: dict[str, object] = field(default_factory=dict)

