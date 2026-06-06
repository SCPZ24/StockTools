from __future__ import annotations

import argparse
import re

from stocktools.infra.paths import Paths


def valid_code(value: str) -> str:
    if not re.fullmatch(r"\d{6}", value):
        raise argparse.ArgumentTypeError("股票代码必须是纯 6 位数字")
    return value


def db_path():
    paths = Paths.resolve()
    paths.ensure_workdir()
    return paths.database_path


def add_thresholds(parser: argparse.ArgumentParser, names: list[str]) -> None:
    for name in names:
        parser.add_argument(f"--{name.replace('_', '-')}", dest=name, type=float)


def compact_options(args, names: list[str]) -> dict:
    return {name: getattr(args, name) for name in names if getattr(args, name, None) is not None}

