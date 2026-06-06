from __future__ import annotations


def print_message(message: str) -> None:
    print(message)


def print_rows(rows: list[dict], empty: str = "没有数据。") -> None:
    if not rows:
        print(empty)
        return
    keys = list(rows[0].keys())
    widths = {key: max(len(str(key)), *(len(str(row.get(key, ""))) for row in rows)) for key in keys}
    print("  ".join(str(key).ljust(widths[key]) for key in keys))
    print("  ".join("-" * widths[key] for key in keys))
    for row in rows:
        print("  ".join(str(row.get(key, "")).ljust(widths[key]) for key in keys))


def print_detail(row: dict | None, empty: str = "没有数据。") -> None:
    if not row:
        print(empty)
        return
    for key, value in row.items():
        print(f"{key}: {value}")

