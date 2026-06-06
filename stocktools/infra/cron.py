from __future__ import annotations

import subprocess


BEGIN = "# StockTools cron begin"
END = "# StockTools cron end"


def _read_crontab() -> str:
    result = subprocess.run(["crontab", "-l"], text=True, capture_output=True, check=False)
    return "" if result.returncode != 0 else result.stdout


def _strip_block(text: str) -> str:
    lines = text.splitlines()
    out = []
    skipping = False
    for line in lines:
        if line.strip() == BEGIN:
            skipping = True
            continue
        if line.strip() == END:
            skipping = False
            continue
        if not skipping:
            out.append(line)
    return "\n".join(out).strip()


def set_stocktools_cron(hour: int, minute: int, command: str) -> None:
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("cron 时间必须在 00:00 到 23:59 之间")
    current = _strip_block(_read_crontab())
    block = f"{BEGIN}\n{minute} {hour} * * * {command}\n{END}"
    new_text = f"{current}\n{block}\n" if current else f"{block}\n"
    subprocess.run(["crontab", "-"], input=new_text, text=True, check=True)

