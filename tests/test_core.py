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
import stocktools.data.providers.akshare_provider as akshare_provider
import stocktools.data.providers.baostock_provider as baostock_provider
import stocktools.data.providers.eastmoney_session as eastmoney_session
import stocktools.services.data_service as data_service
import stocktools.services.find_service as find_service_module
from stocktools.ai.alert_analyst import AlertAnalyst
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
from stocktools.tui.app import StockToolsApp, _ST_THEME
from stocktools.tui.screens.holdings import HoldingsTab
from stocktools.tui.screens.scan import ScanTab
from stocktools.tui.screens.watchlist import WatchlistTab
from stocktools.tui.stock_style import stock_name_cell
from stocktools.tui.widgets.stock_table import StockDataTable
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
    assert {"daily_kline", "watchlist", "holdings", "ai_logs", "concept_index", "concept_kline", "daily_hotspot"}.issubset(tables)

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
    assert [row["content"] for row in logs.get_recent("600519", "watch", 2)] == ["new", "old"]

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


def test_kline_repo_reports_latest_close_direction(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    kline = KlineRepo(paths.database_path)
    kline.bulk_insert(
        [
            {"code": "600519", "name": "贵州茅台", "date": "2026-06-01", "open": 10, "close": 10, "high": 11, "low": 9, "volume": 1000},
            {"code": "600519", "name": "贵州茅台", "date": "2026-06-02", "open": 10, "close": 12, "high": 13, "low": 9, "volume": 1000},
            {"code": "000001", "name": "平安银行", "date": "2026-06-01", "open": 10, "close": 10, "high": 11, "low": 9, "volume": 1000},
            {"code": "000001", "name": "平安银行", "date": "2026-06-02", "open": 10, "close": 9, "high": 11, "low": 8, "volume": 1000},
            {"code": "300001", "name": "特锐德", "date": "2026-06-01", "open": 10, "close": 10, "high": 11, "low": 9, "volume": 1000},
            {"code": "300001", "name": "特锐德", "date": "2026-06-02", "open": 10, "close": 10, "high": 11, "low": 9, "volume": 1000},
        ]
    )

    assert kline.get_latest_close_direction("600519") == "up"
    assert kline.get_latest_close_direction("000001") == "down"
    assert kline.get_latest_close_direction("300001") == "flat"
    assert kline.get_latest_close_direction("688001") is None


def test_stock_name_cell_uses_a_share_price_colors():
    class FakeRepo:
        def __init__(self, direction: str | None) -> None:
            self.direction = direction

        def get_latest_close_direction(self, code: str) -> str | None:
            return self.direction

    assert stock_name_cell(FakeRepo("up"), "600519", "贵州茅台").style == "#e60012"
    assert stock_name_cell(FakeRepo("down"), "600519", "贵州茅台").style == "#009900"
    assert stock_name_cell(FakeRepo("flat"), "600519", "贵州茅台").style == "white"
    assert stock_name_cell(FakeRepo(None), "600519", "贵州茅台").style == "white"


def test_tui_theme_uses_fully_transparent_background_layers(tmp_path: Path, monkeypatch):
    assert _ST_THEME.background == "transparent"
    assert _ST_THEME.surface == "transparent"
    assert _ST_THEME.panel == "transparent"
    assert _ST_THEME.boost == "transparent"
    assert _ST_THEME.variables["block-cursor-background"] == "transparent"
    assert _ST_THEME.variables["input-cursor-background"] == "transparent"
    assert _ST_THEME.variables["input-selection-background"] == "transparent"
    assert _ST_THEME.variables["screen-selection-background"] == "transparent"
    assert _ST_THEME.variables["border"] == "white"
    assert _ST_THEME.variables["border-blurred"] == "white"
    assert _ST_THEME.ansi is False

    init_paths(tmp_path, monkeypatch)
    app = StockToolsApp()
    assert app.ansi_color is True


def test_tui_docs_describe_transparent_kline_chart_with_volume_without_mas():
    doc = Path("docs/TUI.md").read_text(encoding="utf-8")

    assert "不渲染 K 线图" not in doc
    assert "透明底色" in doc
    assert "成交量" in doc
    assert "不叠加均线" in doc
    assert "MA5" not in doc
    assert "MA20" not in doc
    assert "MA60" not in doc


def test_kline_chart_render_includes_price_and_volume_without_ma_layers():
    from rich.style import Style
    from stocktools.tui.widgets.kline_chart import build_kline_chart_text

    df = pd.DataFrame(make_rows("600519", "贵州茅台", 180))

    chart = build_kline_chart_text("600519", "贵州茅台", df, 80, 24)
    plain = chart.plain

    assert "600519" in plain
    assert "贵州茅台" in plain
    assert "MA5" not in plain
    assert "MA20" not in plain
    assert "MA60" not in plain
    assert "成交量" in plain
    assert "2025-" in plain
    assert "\x1b" not in plain
    for span in chart.spans:
        style = Style.parse(span.style) if isinstance(span.style, str) else span.style
        assert style.bgcolor is None


def test_kline_chart_uses_available_width_for_more_than_120_candles():
    from stocktools.tui.widgets.kline_chart import _prepare_visible_klines

    df = pd.DataFrame(make_rows("600519", "贵州茅台", 220))

    visible = _prepare_visible_klines(df, 180)

    assert len(visible) > 120
    assert len(visible) == 171


def test_kline_chart_render_handles_empty_and_tiny_sizes():
    from stocktools.tui.widgets.kline_chart import build_kline_chart_text

    empty = build_kline_chart_text("600519", "贵州茅台", pd.DataFrame(), 80, 24)
    tiny = build_kline_chart_text("600519", "贵州茅台", pd.DataFrame(make_rows(days=30)), 40, 12)

    assert "暂无 K 线数据" in empty.plain
    assert "尺寸不足" in tiny.plain


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


def test_akshare_provider_uses_direct_eastmoney_request(monkeypatch):
    sessions = []
    requested = []

    class FakeResponse:
        def json(self):
            return {
                "data": {
                    "total": 2,
                    "diff": [
                        {"f12": "600519", "f14": "贵州茅台", "f17": 10, "f2": 11, "f15": 12, "f16": 9, "f5": 1000},
                        {"f12": "000001", "f14": "平安银行", "f17": 20, "f2": 21, "f15": 22, "f16": 19, "f5": 2000},
                    ],
                }
            }

        def raise_for_status(self):
            return None

    class FakeSession:
        def __init__(self):
            self.trust_env = True
            sessions.append(self)

        def get(self, url, params, timeout, headers=None):
            requested.append((url, dict(params), timeout, self.trust_env))
            return FakeResponse()

    monkeypatch.setattr(eastmoney_session.requests, "Session", FakeSession)

    rows = akshare_provider.AkshareProvider().fetch_daily_all(date(2026, 6, 9))

    assert [session.trust_env for session in sessions] == [False]
    assert requested[0][3] is False
    assert requested[0][0] == "https://82.push2.eastmoney.com/api/qt/clist/get"
    assert requested[0][1]["fs"] == "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048"
    assert rows == [
        {"code": "600519", "name": "贵州茅台", "date": "2026-06-09", "open": 10.0, "close": 11.0, "high": 12.0, "low": 9.0, "volume": 1000.0},
        {"code": "000001", "name": "平安银行", "date": "2026-06-09", "open": 20.0, "close": 21.0, "high": 22.0, "low": 19.0, "volume": 2000.0},
    ]


def test_akshare_provider_fetches_all_eastmoney_pages(monkeypatch):
    requested_pages = []

    def item(code):
        return {"f12": code, "f14": f"股票{code}", "f17": 10, "f2": 11, "f15": 12, "f16": 9, "f5": 1000}

    class FakeResponse:
        def __init__(self, page):
            self.page = page

        def json(self):
            return {
                "data": {
                    "total": 101,
                    "diff": [item("600001")] if self.page == "1" else [item("600002")],
                }
            }

        def raise_for_status(self):
            return None

    class FakeSession:
        trust_env = False

        def get(self, url, params, timeout, headers=None):
            requested_pages.append(params["pn"])
            return FakeResponse(params["pn"])

    monkeypatch.setattr(eastmoney_session.requests, "Session", FakeSession)

    rows = akshare_provider.AkshareProvider().fetch_daily_all(date(2026, 6, 9))

    assert requested_pages == ["1", "2"]
    assert [row["code"] for row in rows] == ["600001", "600002"]


def test_akshare_provider_falls_back_to_next_eastmoney_host(monkeypatch):
    requested_urls = []

    class FakeResponse:
        def json(self):
            return {
                "data": {
                    "total": 1,
                    "diff": [{"f12": "600519", "f14": "贵州茅台", "f17": 10, "f2": 11, "f15": 12, "f16": 9, "f5": 1000}],
                }
            }

        def raise_for_status(self):
            return None

    class FakeSession:
        trust_env = False

        def get(self, url, params, timeout, headers=None):
            requested_urls.append((url, headers))
            if len(requested_urls) <= 2:
                raise eastmoney_session.requests.exceptions.ConnectionError("first host closed")
            return FakeResponse()

    monkeypatch.setattr(eastmoney_session.requests, "Session", FakeSession)

    rows = akshare_provider.AkshareProvider().fetch_daily_all(date(2026, 6, 9))

    assert requested_urls[0][0] != requested_urls[1][0]
    assert requested_urls[1][1]["Referer"] == "https://quote.eastmoney.com/center/gridlist.html"
    assert rows[0]["code"] == "600519"


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

    result = DataService(paths.database_path, enable_concepts=False).update_daily()

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

    result = DataService(paths.database_path, enable_concepts=False).update_daily()
    df = KlineRepo(paths.database_path).get_klines("600519")

    assert result == {"rows": 1, "date": "2026-06-05", "status": "updated"}
    assert list(df["date"]) == ["2026-06-04", "2026-06-05"]
    assert float(df.iloc[-1]["close"]) == 12.34


def test_update_daily_falls_back_to_per_stock_when_akshare_is_blocked(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    rows = make_rows(days=1)
    rows[0]["date"] = "2026-06-04"
    KlineRepo(paths.database_path).bulk_insert(rows)

    class FakeDate:
        @classmethod
        def today(cls):
            return date(2026, 6, 5)

    class FakeAkshareProvider:
        def fetch_daily_all(self, trade_date=None):
            raise RuntimeError("Eastmoney 行情请求失败")

    class FakeBaostockProvider:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def list_stocks(self):
            return [{"code": "600519", "bs_code": "sh.600519", "name": "贵州茅台"}]

        def fetch_history(self, code, start, end, name=None):
            assert start == end == "2026-06-05"
            return [
                {"code": "600519", "name": "贵州茅台", "date": "2026-06-05",
                 "open": 10, "close": 18.88, "high": 19, "low": 9, "volume": 1000}
            ]

    fallback_called = []
    monkeypatch.setattr(data_service, "date", FakeDate)
    monkeypatch.setattr(data_service, "AkshareProvider", FakeAkshareProvider)
    monkeypatch.setattr(data_service, "BaostockProvider", FakeBaostockProvider)

    result = DataService(paths.database_path, enable_concepts=False).update_daily(
        on_fallback=lambda start, end: fallback_called.append((start, end))
    )
    df = KlineRepo(paths.database_path).get_klines("600519")

    assert result == {"rows": 1, "date": "2026-06-05", "status": "fallback", "stocks": 1, "start": "2026-06-05"}
    assert fallback_called == [("2026-06-05", "2026-06-05")]
    assert list(df["date"]) == ["2026-06-04", "2026-06-05"]
    assert float(df.iloc[-1]["close"]) == 18.88


def test_run_shard_fetches_writes_and_reports_progress(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)

    class FakeBaostockProvider:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def fetch_history(self, code, start, end, name=None):
            assert start == end == "2026-06-05"
            return [
                {"code": code.split(".")[-1], "name": name, "date": "2026-06-05",
                 "open": 10, "close": 11, "high": 12, "low": 9, "volume": 1000}
            ]

    monkeypatch.setattr(data_service, "BaostockProvider", FakeBaostockProvider)
    shard = [
        {"code": "600519", "bs_code": "sh.600519", "name": "贵州茅台"},
        {"code": "000001", "bs_code": "sz.000001", "name": "平安银行"},
    ]
    ticks = []
    result = data_service._run_shard(str(paths.database_path), shard, "2026-06-05", "2026-06-05", lambda: ticks.append(1))

    assert result == {"stocks": 2, "rows": 2}
    assert ticks == [1, 1]
    assert KlineRepo(paths.database_path).get_latest_date() == "2026-06-05"


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


def test_tui_kline_chart_visibility_tracks_terminal_width(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STOCKTOOLS_HOME", str(tmp_path / "work"))

    async def run_check():
        from stocktools.tui.widgets.kline_chart import KlineChart

        wide_app = StockToolsApp()
        async with wide_app.run_test(size=(170, 32)):
            assert wide_app.query_one(WatchlistTab).query_one(KlineChart).display is True

        narrow_app = StockToolsApp()
        async with narrow_app.run_test(size=(120, 32)):
            assert narrow_app.query_one(WatchlistTab).query_one(KlineChart).display is False

    asyncio.run(run_check())


def test_tui_kline_chart_tracks_selected_watchlist_stock(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    KlineRepo(paths.database_path).bulk_insert(make_rows("600519", "贵州茅台", 180))
    RecordService(paths.database_path).add("600519")

    async def run_check():
        from stocktools.tui.widgets.kline_chart import KlineChart

        app = StockToolsApp()
        async with app.run_test(size=(170, 32)) as pilot:
            await pilot.pause()
            chart = app.query_one(WatchlistTab).query_one(KlineChart)
            assert chart.selected_code == "600519"

    asyncio.run(run_check())


def test_tui_stock_tables_share_stock_rendering_layer(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STOCKTOOLS_HOME", str(tmp_path / "work"))

    async def run_check():
        app = StockToolsApp()
        async with app.run_test():
            assert isinstance(app.query_one(WatchlistTab).query_one("#left-panel"), StockDataTable)
            assert isinstance(app.query_one(HoldingsTab).query_one("#left-panel"), StockDataTable)
            assert isinstance(app.query_one(ScanTab).query_one("#scan-results"), StockDataTable)

    asyncio.run(run_check())


def test_tui_stock_tables_keep_cell_colors_under_cursor():
    table = StockDataTable()

    assert table.cursor_foreground_priority == "renderable"


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


def test_alert_analyst_uses_holding_entry_price_as_cost_price():
    captured = {}

    class FakeLLMClient:
        def invoke(self, messages):
            captured["messages"] = messages
            return "analysis: 趋势稳定\nconclusion: 止损：92；止盈：128"

    analyst = AlertAnalyst(FakeLLMClient())
    holding = {"code": "600519", "name": "贵州茅台", "entry_price": 100.5, "quantity": 200}
    klines = pd.DataFrame(make_rows("600519", "贵州茅台", 20))

    analyst.analyze(holding, klines)

    user_prompt = captured["messages"][1]["content"]
    assert "- 买入价：100.5" in user_prompt
    assert "- 买入价：未知" not in user_prompt


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
