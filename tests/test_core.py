from __future__ import annotations

import asyncio
import os
import sqlite3
import stat
import time
import types
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from stocktools.config.model_config_repo import ModelConfigRepo
import stocktools.ai.client as ai_client
import stocktools.data.db as data_db
import stocktools.data.providers.baostock_provider as baostock_provider
import stocktools.services.data_service as data_service
import stocktools.services.find_service as find_service_module
from stocktools.ai.client import LLMClient
from stocktools.data.repos.ai_logs_repo import AiLogsRepo
from stocktools.data.repos.holdings_repo import HoldingsRepo
from stocktools.data.repos.kline_repo import KlineRepo
from stocktools.data.repos.watchlist_repo import WatchlistRepo
from stocktools.infra.paths import Paths
from stocktools.scanners.registry import get_scanner
from stocktools.services.alert_service import AlertService
from stocktools.services.data_service import DataService
from stocktools.services.find_service import FindService
from stocktools.services.record_service import RecordService
from stocktools.services.watch_service import WatchService
from stocktools.tui.app import StockToolsApp
from stocktools.tui.screens.scan import ScanTab
from textual.widgets import DataTable


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


def test_kline_repo_read_methods_work_when_database_directory_is_not_writable(tmp_path: Path):
    db_dir = tmp_path / "readonly-db"
    db_dir.mkdir()
    db_path = db_dir / "database.db"
    paths = Paths(db_dir)
    paths.init_databases()
    kline = KlineRepo(db_path)
    kline.bulk_insert(make_rows(days=3))
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
    db_dir.chmod(stat.S_IREAD | stat.S_IEXEC)
    try:
        assert len(kline.get_klines("600519")) == 3
        assert kline.list_codes() == [{"code": "600519", "name": "贵州茅台"}]
        assert kline.get_latest_date() == "2025-01-03"
        assert kline.get_latest_name("600519") == "贵州茅台"
    finally:
        db_dir.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)


def test_connect_readonly_opens_database_as_immutable_uri(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "database.db"
    seen = {}
    real_connect = sqlite3.connect

    def fake_connect(path, **kwargs):
        seen["path"] = path
        seen["kwargs"] = kwargs
        conn = real_connect(":memory:")
        conn.execute("CREATE TABLE daily_kline(code TEXT)")
        return conn

    monkeypatch.setattr(data_db.sqlite3, "connect", fake_connect)

    with data_db.connect_readonly(db_path) as conn:
        conn.execute("SELECT count(*) FROM daily_kline").fetchone()

    assert seen["kwargs"] == {"uri": True}
    assert seen["path"].startswith("file://")
    assert "mode=ro" in seen["path"]
    assert "immutable=1" in seen["path"]


def test_scanners_match_synthetic_data():
    # 爆量吸筹: a stock that fell from ~10 to a flat low base ~7, then in the
    # last few sessions absorbs heavy volume on up-days while price stays low.
    vol_rows = make_rows(days=130)
    for i, row in enumerate(vol_rows):
        if i < 60:
            close = 10.0 - (i / 60) * 3.0  # decline 10 -> 7
        else:
            close = 7.0  # flat low base
        volume = 1000
        if i >= 125:  # last 5 days: explosive volume, contained price
            close = 7.0 + (i - 124) * 0.06
            volume = 3500
        row["close"] = round(close, 2)
        row["open"] = round(close - 0.05, 2)
        row["high"] = round(close + 0.1, 2)
        row["low"] = round(close - 0.1, 2)
        row["volume"] = volume
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


def test_baostock_list_stocks_falls_back_from_empty_non_trading_day(monkeypatch):
    queried_days = []

    class FakeResult:
        def __init__(self, data):
            self.data = data

        def get_data(self):
            return self.data

    class FakeBaostock:
        def query_all_stock(self, day):
            queried_days.append(day)
            if len(queried_days) == 1:
                return FakeResult(pd.DataFrame())
            return FakeResult(
                pd.DataFrame(
                    [
                        {"code": "sh.600519", "code_name": "贵州茅台"},
                        {"code": "sz.000001", "code_name": "平安银行"},
                    ]
                )
            )

    class FakeDateTime:
        @classmethod
        def now(cls):
            return date(2026, 6, 7)

    monkeypatch.setattr(baostock_provider, "datetime", FakeDateTime)
    provider = baostock_provider.BaostockProvider()
    provider.bs = FakeBaostock()

    assert provider.list_stocks() == [
        {"code": "600519", "bs_code": "sh.600519", "name": "贵州茅台"},
        {"code": "000001", "bs_code": "sz.000001", "name": "平安银行"},
    ]
    assert queried_days == ["2026-06-06", "2026-06-05"]


def test_box_scanner_handles_full_market_scale_without_pandas_hot_loop():
    scanner = get_scanner("box")
    frames = [pd.DataFrame(make_rows(f"{600000 + i:06d}", "测试", 242)) for i in range(300)]

    start = time.perf_counter()
    for df in frames:
        scanner.detect(df)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.5


def test_update_daily_skips_when_weekend_snapshot_is_already_current(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    rows = make_rows(days=1)
    rows[0]["date"] = "2026-06-05"
    KlineRepo(paths.database_path).bulk_insert(rows)

    class FakeDate:
        @classmethod
        def today(cls):
            return date(2026, 6, 7)

    class FakeAkshareProvider:
        def fetch_daily_all(self, trade_date=None):
            raise AssertionError("provider should not be called when local data is already current")

    monkeypatch.setattr(data_service, "date", FakeDate)
    monkeypatch.setattr(data_service, "AkshareProvider", FakeAkshareProvider)

    result = DataService(paths.database_path).update_daily()

    assert result == {"rows": 0, "date": "2026-06-05", "status": "latest"}
    assert len(KlineRepo(paths.database_path).get_klines("600519")) == 1


def test_update_daily_uses_previous_weekday_as_snapshot_date_on_weekend(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    rows = make_rows(days=1)
    rows[0]["date"] = "2026-06-04"
    KlineRepo(paths.database_path).bulk_insert(rows)

    class FakeDate:
        @classmethod
        def today(cls):
            return date(2026, 6, 7)

    class FakeAkshareProvider:
        def fetch_daily_all(self, trade_date=None):
            assert trade_date == date(2026, 6, 5)
            row = make_rows(days=1)[0]
            row["date"] = trade_date.isoformat()
            row["close"] = 12.34
            return [row]

    monkeypatch.setattr(data_service, "date", FakeDate)
    monkeypatch.setattr(data_service, "AkshareProvider", FakeAkshareProvider)

    result = DataService(paths.database_path).update_daily()
    df = KlineRepo(paths.database_path).get_klines("600519")

    assert result == {"rows": 1, "date": "2026-06-05", "status": "updated"}
    assert list(df["date"]) == ["2026-06-04", "2026-06-05"]
    assert float(df.iloc[-1]["close"]) == 12.34


def test_find_service_iter_scan_yields_first_match_before_scanning_all(monkeypatch):
    calls = []

    class FakeRepo:
        def list_codes(self):
            return [
                {"code": "600001", "name": "先命中"},
                {"code": "600002", "name": "后扫描"},
            ]

        def get_klines(self, code, n_days=None):
            calls.append(code)
            return pd.DataFrame(make_rows(code, code, 140))

    class FakeScanner:
        def detect(self, df, **options):
            from stocktools.scanners.results import ScanResult

            return ScanResult(True, "fake", {"score": len(calls)})

    monkeypatch.setattr(find_service_module, "get_scanner", lambda name: FakeScanner())
    service = FindService(":memory:")
    service.kline_repo = FakeRepo()

    stream = service.iter_scan("fake")
    first = next(stream)

    assert first == {"code": "600001", "name": "先命中", "pattern": "fake", "score": 1}
    assert calls == ["600001"]
    assert list(stream)[0]["code"] == "600002"


def test_tui_scan_tab_append_scan_result_updates_results_and_table(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STOCKTOOLS_HOME", str(tmp_path / "work"))

    async def run_check():
        app = StockToolsApp()
        async with app.run_test():
            tab = app.query_one(ScanTab)
            app._switch_tab(2)
            item = {"code": "600519", "name": "贵州茅台", "pattern": "box", "score": 12.3, "price": 10.0}

            tab._append_scan_result(item)

            table = tab.query_one("#scan-results", DataTable)
            assert tab._results == [item]
            assert table.row_count == 1

    asyncio.run(run_check())


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
