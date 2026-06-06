from __future__ import annotations

from .base import BaseScanner
from .box_break import BoxBreakScanner
from .channel import ChannelScanner
from .independent import IndependentScanner
from .volume_absorb import VolumeAbsorbScanner


SCANNER_CLASSES: dict[str, type[BaseScanner]] = {
    "box_break": BoxBreakScanner,
    "channel": ChannelScanner,
    "volume_absorb": VolumeAbsorbScanner,
    "independent": IndependentScanner,
}


def get_scanner(name: str) -> BaseScanner:
    try:
        return SCANNER_CLASSES[name]()
    except KeyError as exc:
        raise ValueError(f"未知扫描器: {name}") from exc


def scanner_names() -> list[str]:
    return list(SCANNER_CLASSES)

