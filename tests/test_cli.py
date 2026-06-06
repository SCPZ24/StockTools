from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from stocktools.data.repos.holdings_repo import HoldingsRepo
from stocktools.data.repos.kline_repo import KlineRepo
from stocktools.data.repos.watchlist_repo import WatchlistRepo
from stocktools.infra.paths import Paths


ROOT = Path(__file__).resolve().parents[1]
ST = ROOT / "st.py"


def run_cli(args: list[str], home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["STOCKTOOLS_HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(ST), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def seed_workdir(home: Path, code: str = "600519") -> None:
    os.environ["STOCKTOOLS_HOME"] = str(home)
    paths = Paths.resolve()
    paths.init_databases()
    start = date(2025, 1, 1)
    rows = []
    for i in range(140):
        price = 10 + i * 0.03
        rows.append(
            {
                "code": code,
                "name": "贵州茅台",
                "date": (start + timedelta(days=i)).isoformat(),
                "open": price,
                "close": price + 0.05,
                "high": price + 0.2,
                "low": price - 0.2,
                "volume": 1000 + i,
            }
        )
    KlineRepo(paths.database_path).bulk_insert(rows)


def test_all_documented_command_groups_expose_help(tmp_path: Path):
    home = tmp_path / "work"
    help_commands = [
        [],
        ["init", "--help"],
        ["update", "--help"],
        ["cron", "set", "--help"],
        ["cron", "remove", "--help"],
        ["config", "--help"],
        ["config", "model", "--help"],
        ["config", "model", "set", "--help"],
        ["config", "model", "show", "--help"],
        ["config", "add", "model", "--help"],
        ["config", "show", "model", "--help"],
        ["find", "--help"],
        ["record", "--help"],
        ["record", "add", "--help"],
        ["record", "show", "--help"],
        ["record", "note", "--help"],
        ["record", "go", "--help"],
        ["record", "list", "--help"],
        ["record", "rm", "--help"],
        ["watch", "--help"],
        ["hold", "--help"],
        ["hold", "in", "--help"],
        ["hold", "out", "--help"],
        ["hold", "set", "--help"],
        ["hold", "show", "--help"],
        ["hold", "list", "--help"],
        ["hold", "history", "--help"],
        ["alert", "--help"],
    ]
    for args in help_commands:
        result = run_cli(["--help"] if not args else args, home)
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout


def test_cli_record_hold_find_csv_and_code_validation(tmp_path: Path):
    home = tmp_path / "work"
    seed_workdir(home)

    bad = run_cli(["hold", "in", "60051", "--price", "100"], home)
    assert bad.returncode == 2
    assert "股票代码必须是纯 6 位数字" in bad.stderr

    added = run_cli(["record", "add", "600519", "-m", "测试"], home)
    assert added.returncode == 0, added.stderr
    assert "600519" in added.stdout

    listed = run_cli(["record", "list"], home)
    assert listed.returncode == 0
    assert "测试" in listed.stdout

    entry = run_cli(["hold", "in", "600519", "--price", "100"], home)
    assert entry.returncode == 0, entry.stderr
    assert "open" in entry.stdout

    out = run_cli(["hold", "out", "600519", "--price", "120"], home)
    assert out.returncode == 0
    assert "已处理 1 条持仓" in out.stdout

    csv_path = tmp_path / "history.csv"
    history = run_cli(["hold", "history", "--near", "1", "--csv", str(csv_path)], home)
    assert history.returncode == 0
    assert csv_path.exists()
    assert "600519" in csv_path.read_text(encoding="utf-8-sig")

    scan_csv = tmp_path / "scan.csv"
    scan = run_cli(
        ["find", "independent", "--excess-return-min", "0", "--drawdown-max", "1", "--recent-return-min", "-1", "--csv", str(scan_csv)],
        home,
    )
    assert scan.returncode == 0, scan.stderr
    assert scan_csv.exists()


def test_cli_config_model_set_and_show(tmp_path: Path):
    home = tmp_path / "work"
    seed_workdir(home)

    set_result = run_cli(
        [
            "config",
            "model",
            "set",
            "--base-url",
            "https://api.example.com",
            "--api-key",
            "secret",
            "--model-name",
            "deepseek-chat",
        ],
        home,
    )
    assert set_result.returncode == 0, set_result.stderr
    assert "模型配置已保存" in set_result.stdout

    show_result = run_cli(["config", "model", "show"], home)
    assert show_result.returncode == 0
    assert "https://api.example.com" in show_result.stdout
    assert "deepseek-chat" in show_result.stdout
    assert "secret" not in show_result.stdout
    assert "******" in show_result.stdout

    alias_set = run_cli(
        [
            "config",
            "add",
            "model",
            "--base-url",
            "https://api2.example.com",
            "--api-key",
            "secret2",
            "--model-name",
            "model-b",
        ],
        home,
    )
    assert alias_set.returncode == 0, alias_set.stderr
    alias_show = run_cli(["config", "show", "model"], home)
    assert alias_show.returncode == 0
    assert "https://api2.example.com" in alias_show.stdout
    assert "model-b" in alias_show.stdout


def test_setup_initializes_databases_and_shell_config_without_cron(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    workdir = tmp_path / "setup-work"
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("STOCKTOOLS_HOME", None)
    result = subprocess.run(
        ["bash", str(ROOT / "setup.sh")],
        cwd=ROOT,
        env=env,
        input=f"{workdir}\nn\nn\n",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (home / ".stock_tools_path").read_text(encoding="utf-8").strip() == str(workdir)
    assert (home / ".zshrc").read_text(encoding="utf-8").count("# StockTools begin") == 1

    db = sqlite3.connect(workdir / "database.db")
    tables = {row[0] for row in db.execute("select name from sqlite_master where type='table'")}
    assert {"daily_kline", "watchlist", "holdings", "ai_logs"}.issubset(tables)

    config = sqlite3.connect(workdir / "config.db")
    config_tables = {row[0] for row in config.execute("select name from sqlite_master where type='table'")}
    assert "model_config" in config_tables
