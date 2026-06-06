from __future__ import annotations

import os
import sqlite3
import types
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from stocktools.config.model_config_repo import ModelConfigRepo
import stocktools.ai.client as ai_client
from stocktools.ai.client import LLMClient
from stocktools.data.repos.ai_logs_repo import AiLogsRepo
from stocktools.data.repos.holdings_repo import HoldingsRepo
from stocktools.data.repos.kline_repo import KlineRepo
from stocktools.data.repos.watchlist_repo import WatchlistRepo
from stocktools.infra.paths import Paths
from stocktools.scanners.registry import get_scanner
from stocktools.services.alert_service import AlertService
from stocktools.services.find_service import FindService
from stocktools.services.record_service import RecordService
from stocktools.services.watch_service import WatchService


def make_rows(code: str = "600519", name: str = "贵州茅台", days: int = 140) -> list[dict]:
    start = date(2025, 1, 1)
    rows = []
    for i in range(days):
        price = 10 + i * 0.03
        rows.append(
            {
                "code": code,
                "name": name,
                "date": (start + timedelta(days=i)).isoformat(),
                "open": price,
                "close": price + 0.05,
                "high": price + 0.2,
                "low": price - 0.2,
                "volume": 1000 + i,
            }
        )
    return rows


def init_paths(tmp_path: Path, monkeypatch) -> Paths:
    home = tmp_path / "work"
    monkeypatch.setenv("STOCKTOOLS_HOME", str(home))
    paths = Paths.resolve()
    paths.ensure_workdir()
    paths.init_databases()
    return paths


def test_paths_env_wins(tmp_path: Path, monkeypatch):
    env_home = tmp_path / "env-home"
    path_file_home = tmp_path / "path-file-home"
    marker = tmp_path / ".stock_tools_path"
    marker.write_text(str(path_file_home), encoding="utf-8")
    monkeypatch.setenv("STOCKTOOLS_HOME", str(env_home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    paths = Paths.resolve()

    assert paths.workdir == env_home
    assert paths.database_path == env_home / "database.db"
    assert paths.config_path == env_home / "config.db"


def test_schema_and_repos_are_idempotent(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    paths.init_databases()

    conn = sqlite3.connect(paths.database_path)
    tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
    assert {"daily_kline", "watchlist", "holdings", "ai_logs"}.issubset(tables)

    config_conn = sqlite3.connect(paths.config_path)
    config_tables = {row[0] for row in config_conn.execute("select name from sqlite_master where type='table'")}
    assert "model_config" in config_tables

    kline = KlineRepo(paths.database_path)
    kline.bulk_insert(make_rows(days=3))
    kline.bulk_insert(make_rows(days=3))
    assert len(kline.get_klines("600519")) == 3

    watch = WatchlistRepo(paths.database_path)
    watch.add("600519", "贵州茅台", "channel", "first")
    watch.update_note("600519", "second", replace=False)
    watch.set_buy_tomorrow("600519", True)
    assert watch.get("600519")["note"] == "first\nsecond"
    assert watch.get("600519")["buy_tomorrow"] == 1
    watch.remove("600519")
    assert watch.get("600519") is None

    holdings = HoldingsRepo(paths.database_path)
    holdings.add_entry("600519", "贵州茅台", 100)
    holdings.add_entry("600519", "贵州茅台", 101)
    assert len(holdings.list_open("600519")) == 2
    holdings.append_reduction_note("600519", 110)
    assert len(holdings.list_open("600519")) == 2
    holdings.close_all_open_by_code("600519", 120)
    assert len(holdings.list_open("600519")) == 0
    assert len(holdings.list_closed()) == 2

    logs = AiLogsRepo(paths.database_path)
    logs.upsert("600519", "watch", "wait", "old", "2026-01-01")
    logs.upsert("600519", "watch", "buy", "new", "2026-01-01")
    assert logs.get_latest("600519", "watch")["content"] == "new"

    config = ModelConfigRepo(paths.config_path)
    config.upsert("https://api.example.com", "secret", "deepseek-chat")
    assert config.get()["model_name"] == "deepseek-chat"


def test_scanners_match_synthetic_data():
    vol_rows = make_rows(days=100)
    for i, row in enumerate(vol_rows):
        if i >= 80:
            row["volume"] = 1200
            row["close"] = 12.0 + (i - 80) * 0.02
            row["open"] = row["close"] - 0.05
            row["high"] = row["close"] + 0.2
            row["low"] = row["close"] - 0.2
        if i >= 95:
            row["volume"] = 3000
            row["close"] = 12.4 + (i - 95) * 0.05
            row["open"] = row["close"] - 0.05
            row["high"] = row["close"] + 0.2
            row["low"] = row["close"] - 0.2
    vol_df = pd.DataFrame(vol_rows)
    assert get_scanner("volume_absorb").detect(vol_df).matched

    strong_rows = make_rows(days=140)
    for i, row in enumerate(strong_rows):
        row["close"] = 10 + i * 0.08
        row["open"] = row["close"] - 0.02
        row["high"] = row["close"] + 0.1
        row["low"] = row["close"] - 0.1
        row["volume"] = 500 if i >= 120 else 2000
    strong_df = pd.DataFrame(strong_rows)
    assert get_scanner("independent").detect(strong_df, baseline_return=0.05).matched


def test_services_scan_record_watch_alert(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    kline = KlineRepo(paths.database_path)
    kline.bulk_insert(make_rows("600519", "贵州茅台", 140))

    find = FindService(paths.database_path)
    assert isinstance(find.scan("independent", {"baseline_return": 0.0}), list)

    record = RecordService(paths.database_path)
    added = record.add("600519", "观察")
    assert added["code"] == "600519"
    assert record.list_all()[0]["note"] == "观察"

    class FakeWatchAnalyst:
        def analyze(self, code, name, patterns, klines):
            from stocktools.ai.models import WatchAnalysis

            return WatchAnalysis(code=code, conclusion="wait", content="wait\n继续观察", analysis_date="2026-01-01")

    watch = WatchService(paths.database_path, FakeWatchAnalyst())
    assert watch.analyze("600519")[0].conclusion == "wait"

    holdings = HoldingsRepo(paths.database_path)
    holdings.add_entry("600519", "贵州茅台", 100, stop_loss=90, take_profit=130)

    class FakeAlertAnalyst:
        def analyze(self, holding, klines):
            from stocktools.ai.models import AlertAnalysis

            return AlertAnalysis(
                code=holding["code"],
                conclusion="hold",
                content="hold\n继续持有，止损 92，目标 128",
                analysis_date="2026-01-01",
                suggested_stop_loss=92,
                suggested_take_profit=128,
            )

    alert = AlertService(paths.database_path, FakeAlertAnalyst())
    result = alert.analyze("600519")[0]
    assert result.suggested_stop_loss == 92
    assert holdings.list_open("600519")[0]["stop_loss"] == 90


def test_llm_client_invokes_openai_compatible_non_streaming_api(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    ModelConfigRepo(paths.config_path).upsert("https://api.example.com", "secret", "model-a")
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = types.SimpleNamespace(content="wait\n继续观察")
            choice = types.SimpleNamespace(message=message)
            return types.SimpleNamespace(choices=[choice])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = types.SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(ai_client, "OpenAI", FakeOpenAI)

    content = LLMClient(paths.config_path).invoke([{"role": "user", "content": "hi"}], temperature=0.1)

    assert content == "wait\n继续观察"
    assert captured["client"] == {"base_url": "https://api.example.com", "api_key": "secret", "timeout": 60.0}
    assert captured["model"] == "model-a"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["temperature"] == 0.1
    assert captured["stream"] is False
