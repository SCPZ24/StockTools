from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseScanner


SCANNER_CLASSES: dict[str, tuple[str, str]] = {
    "box": ("stocktools.scanners.box", "BoxScanner"),
    "channel": ("stocktools.scanners.channel", "ChannelScanner"),
    "volume_absorb": ("stocktools.scanners.volume_absorb", "VolumeAbsorbScanner"),
    "independent": ("stocktools.scanners.independent", "IndependentScanner"),
    "ma_alignment": ("stocktools.scanners.ma_alignment", "MAAlignmentScanner"),
}


def get_scanner(name: str) -> "BaseScanner":
    try:
        module_name, class_name = SCANNER_CLASSES[name]
    except KeyError as exc:
        raise ValueError(f"未知扫描器: {name}") from exc
    scanner_cls = getattr(import_module(module_name), class_name)
    return scanner_cls()


def scanner_names() -> list[str]:
    return list(SCANNER_CLASSES)
