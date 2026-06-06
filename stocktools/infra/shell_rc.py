from __future__ import annotations

from pathlib import Path


BEGIN = "# StockTools begin"
END = "# StockTools end"


def default_rc_path() -> Path:
    zsh = Path.home() / ".zshrc"
    if zsh.exists() or not (Path.home() / ".bashrc").exists():
        return zsh
    return Path.home() / ".bashrc"


def has_stocktools_block(path: Path | None = None) -> bool:
    rc = path or default_rc_path()
    return rc.exists() and BEGIN in rc.read_text(encoding="utf-8", errors="ignore")


def append_stocktools_block(command_path: str, path: Path | None = None) -> bool:
    rc = path or default_rc_path()
    if has_stocktools_block(rc):
        return False
    block = f'\n{BEGIN}\nfunction st() {{ python3 "{command_path}" "$@"; }}\n{END}\n'
    rc.parent.mkdir(parents=True, exist_ok=True)
    with rc.open("a", encoding="utf-8") as f:
        f.write(block)
    return True

