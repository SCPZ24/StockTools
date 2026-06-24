from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import types
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

import stocktools.ai.client as ai_client
import stocktools.services.data_service as data_service
from stocktools.ai.alert_analyst import AlertAnalyst
from stocktools.ai.client import LLMClient
from stocktools.ai.ensemble import AlertEnsemble, WatchEnsemble
from stocktools.ai.models import AlertAnalysis, WatchAnalysis
from stocktools.ai.watch_analyst import WatchAnalyst
from stocktools.data.providers.eastmoney_concept_provider import EastmoneyConceptProvider
from stocktools.data.providers.eastmoney_session import EASTMONEY_CLIST_URLS, EastmoneySession
from stocktools.data.repos.ai_logs_repo import AiLogsRepo
from stocktools.data.repos.concept_hotspot_repo import ConceptHotspotRepo
from stocktools.data.repos.concept_index_repo import ConceptIndexRepo
from stocktools.data.repos.concept_kline_repo import ConceptKlineRepo
from stocktools.infra.paths import Paths
from stocktools.services.concept_service import ConceptService
from stocktools.services.data_service import DataService


ROOT = Path(__file__).resolve().parents[1]
ST = ROOT / "st.py"


def init_paths(tmp_path: Path, monkeypatch) -> Paths:
    home = tmp_path / "work"
    monkeypatch.setenv("STOCKTOOLS_HOME", str(home))
    paths = Paths.resolve()
    paths.init_databases()
    return paths


def concept_rows(code: str = "BK0001", days: int = 140, start: date = date(2026, 1, 1)) -> list[dict]:
    rows = []
    for i in range(days):
        price = 100 + i
        rows.append(
            {
                "code": code,
                "date": (start + timedelta(days=i)).isoformat(),
                "open": price,
                "close": price + 1,
                "high": price + 2,
                "low": price - 1,
                "volume": 1000 + i,
                "amount": 1_000_000 + i,
                "pct_chg": 1.0 + i / 100,
                "turnover": 2.0,
            }
        )
    return rows


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


def test_schema_adds_concept_tables_and_ai_logs_append_columns(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)

    with sqlite3.connect(paths.database_path) as conn:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        ai_cols = {row[1] for row in conn.execute("pragma table_info(ai_logs)")}

    assert {"concept_index", "concept_kline", "daily_hotspot"}.issubset(tables)
    assert {"confidence", "degraded", "votes"}.issubset(ai_cols)

    logs = AiLogsRepo(paths.database_path)
    logs.upsert("600519", "watch", "wait", "old", "2026-01-01", confidence=0.6, degraded=True)
    logs.upsert("600519", "watch", "buy", "new", "2026-01-01", confidence=0.8, degraded=False)
    recent = logs.get_recent("600519", "watch", 3)

    assert [row["content"] for row in recent[:2]] == ["new", "old"]
    assert recent[0]["confidence"] == 0.8
    assert recent[0]["degraded"] == 0


def test_schema_migrates_legacy_ai_logs_unique_table(tmp_path: Path):
    db_path = tmp_path / "database.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE ai_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                type TEXT NOT NULL,
                conclusion TEXT NOT NULL,
                content TEXT NOT NULL,
                analysis_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (code, type, analysis_date)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO ai_logs(code, type, conclusion, content, analysis_date, created_at)
            VALUES ('600519', 'watch', 'wait', 'legacy', '2026-01-01', '2026-01-01 10:00:00')
            """
        )

    from stocktools.data.db import init_db

    init_db(db_path)
    logs = AiLogsRepo(db_path)
    logs.insert("600519", "watch", "buy", "fresh", "2026-01-01")

    recent = logs.get_recent("600519", "watch", 5)
    assert [row["content"] for row in recent] == ["fresh", "legacy"]


def test_eastmoney_session_is_direct_and_falls_back_to_next_host(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"diff": [{"f12": "BK0001"}], "total": 1}}

    class FakeSession:
        def __init__(self):
            self.trust_env = True

        def get(self, url, params, timeout, headers=None):
            calls.append((url, dict(params), timeout, self.trust_env, headers))
            if len(calls) == 1:
                raise RuntimeError("first host failed")
            return FakeResponse()

    import stocktools.data.providers.eastmoney_session as eastmoney_session

    monkeypatch.setattr(eastmoney_session.requests, "Session", FakeSession)

    payload = EastmoneySession(EASTMONEY_CLIST_URLS[:2]).get_json({"pn": "1"})

    assert payload["data"]["diff"][0]["f12"] == "BK0001"
    assert calls[0][3] is False
    assert calls[1][3] is False
    assert calls[0][0] != calls[1][0]


def test_concept_provider_parses_list_and_kline_records(monkeypatch):
    class FakeEastmoney:
        def __init__(self):
            self.calls = []

        def get_json(self, params):
            self.calls.append(dict(params))
            if "secid" in params:
                return {
                    "data": {
                        "klines": [
                            "2026-06-01,10,11,12,9,1000,200000000,3.0,2.5,0.2,1.5",
                            "bad,row",
                        ]
                    }
                }
            return {
                "data": {
                    "diff": [
                        {"f12": "BK0001", "f14": "测试概念", "f2": 123.4, "f3": 5.6, "f6": 987654321},
                        {"f12": "BK0002", "f14": "坏概念", "f2": "-", "f3": "-", "f6": "-"},
                    ]
                }
            }

    fake = FakeEastmoney()
    provider = EastmoneyConceptProvider(session=fake)

    concepts = provider.fetch_concepts()
    klines = provider.fetch_kline("BK0001", "2026-06-01", "2026-06-02")

    assert concepts == [
        {"code": "BK0001", "name": "测试概念", "price": 123.4, "pct_chg": 5.6, "amount": 987654321.0}
    ]
    assert klines == [
        {
            "code": "BK0001",
            "date": "2026-06-01",
            "open": 10.0,
            "close": 11.0,
            "high": 12.0,
            "low": 9.0,
            "volume": 1000.0,
            "amount": 200000000.0,
            "pct_chg": 2.5,
            "turnover": 1.5,
        }
    ]
    assert fake.calls[0]["fs"] == "m:90 t:3 f:!50"
    assert fake.calls[1]["secid"] == "90.BK0001"


def test_concept_repos_sync_rank_and_hotspot_rules(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    index = ConceptIndexRepo(paths.database_path)
    kline = ConceptKlineRepo(paths.database_path)
    hotspot = ConceptHotspotRepo(paths.database_path)

    assert index.sync([{"code": "BK0001", "name": "概念A"}, {"code": "BK0002", "name": "概念B"}]) == {
        "inserted": 2,
        "renamed": 0,
        "deactivated": 0,
    }
    assert index.sync([{"code": "BK0001", "name": "概念A改名"}, {"code": "BK0003", "name": "概念C"}]) == {
        "inserted": 1,
        "renamed": 1,
        "deactivated": 1,
    }
    assert index.get("BK0002")["active"] == 0

    kline.bulk_upsert(concept_rows("BK0001", 12))
    kline.bulk_upsert(concept_rows("BK0003", 12))
    base = date(2026, 1, 1)
    for day in range(10):
        current = (base + timedelta(days=day)).isoformat()
        rows = [{"code": "BK0001", "pct_chg": 1.0}, {"code": "BK0003", "pct_chg": 0.9}]
        if day in (0, 1, 2, 3, 4, 5):
            rows.append({"code": "BK0004", "pct_chg": 0.8})
        hotspot.replace_date(current, rows)

    service = ConceptService(paths.database_path, provider=None)
    hot = service.hot()

    assert hot[0]["code"] == "BK0001"
    assert hot[0]["hit_7_of_10"] is True
    assert hot[0]["hit_3_consecutive"] is True
    assert {item["code"] for item in hot} == {"BK0001", "BK0003"}


def test_concept_service_show_reports_insufficient_and_ma_alignment(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    ConceptIndexRepo(paths.database_path).sync([{"code": "BK0001", "name": "测试概念"}])
    kline = ConceptKlineRepo(paths.database_path)
    kline.bulk_upsert(concept_rows("BK0001", 30))

    service = ConceptService(paths.database_path, provider=None)
    detail = service.show("BK0001")
    assert detail["trend"] == "数据不足"

    strong = concept_rows("BK0001", 150)
    for i, row in enumerate(strong):
        row["close"] = 10 + i * 0.3
        row["open"] = row["close"] - 0.1
        row["high"] = row["close"] + 0.2
        row["low"] = row["close"] - 0.2
        row["volume"] = 3000 if i >= 130 else 1000
    kline.bulk_upsert(strong)

    detail = service.show("BK0001")
    assert detail["trend"].startswith("多头排列")
    assert detail["returns"]["ret_5d"] > 0


def test_concept_cli_help_and_db_backed_commands(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    ConceptIndexRepo(paths.database_path).sync([{"code": "BK0001", "name": "测试概念"}])
    ConceptKlineRepo(paths.database_path).bulk_upsert(concept_rows("BK0001", 140))
    ConceptHotspotRepo(paths.database_path).replace_date("2026-01-10", [{"code": "BK0001", "pct_chg": 3.2}])

    for args in (["concept", "--help"], ["concept", "top", "--help"], ["concept", "hot", "--help"], ["concept", "show", "--help"]):
        result = run_cli(args, paths.workdir)
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout

    bad = run_cli(["concept", "show", "BAD"], paths.workdir)
    assert bad.returncode == 2
    assert "概念代码必须形如 BK1128" in bad.stderr

    top = run_cli(["concept", "top", "-n", "1"], paths.workdir)
    assert top.returncode == 0, top.stderr
    assert "BK0001" in top.stdout
    assert "测试概念" in top.stdout


def test_update_daily_intraday_guard_blocks_providers_and_force_bypasses(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    calls = []

    class FakeDate:
        @classmethod
        def today(cls):
            return date(2026, 6, 24)

    class FakeDatetime:
        @classmethod
        def now(cls):
            return datetime(2026, 6, 24, 10, 0)

    class FakeAkshareProvider:
        def fetch_daily_all(self, trade_date=None):
            calls.append("akshare")
            return []

    class FakeBaostockProvider:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def list_stocks(self):
            return []

    monkeypatch.setattr(data_service, "date", FakeDate)
    monkeypatch.setattr(data_service, "datetime", FakeDatetime)
    monkeypatch.setattr(data_service, "AkshareProvider", FakeAkshareProvider)
    monkeypatch.setattr(data_service, "BaostockProvider", FakeBaostockProvider)

    blocked = DataService(paths.database_path, enable_concepts=False).update_daily()
    assert blocked["status"] == "blocked_intraday"
    assert calls == []

    forced = DataService(paths.database_path, enable_concepts=False).update_daily(force=True)
    assert forced["status"] in {"fallback", "updated", "latest"}
    assert calls == ["akshare"]


def test_llm_client_accepts_response_format(tmp_path: Path, monkeypatch):
    paths = init_paths(tmp_path, monkeypatch)
    from stocktools.config.model_config_repo import ModelConfigRepo

    ModelConfigRepo(paths.config_path).upsert("https://api.example.com", "secret", "model-a")
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = types.SimpleNamespace(content='{"summary":"ok"}')
            choice = types.SimpleNamespace(message=message)
            return types.SimpleNamespace(choices=[choice])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(ai_client, "OpenAI", FakeOpenAI)

    content = LLMClient(paths.config_path).invoke(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )

    assert content == '{"summary":"ok"}'
    assert captured["response_format"] == {"type": "json_object"}


def test_watch_and_alert_analysts_parse_json_and_retry_invalid_output():
    class FakeClient:
        def __init__(self, responses):
            self.responses = list(responses)
            self.calls = []

        def invoke(self, messages, temperature=0.2, response_format=None):
            self.calls.append((messages, response_format))
            return self.responses.pop(0)

    watch_client = FakeClient(["not json", '{"trend":"up","conclusion":"buy","confidence":0.7,"analysis":"结构转强"}'])
    watch = WatchAnalyst(watch_client).analyze("600519", "贵州茅台", "ignored-pattern", pd.DataFrame(concept_rows(days=80)))

    assert watch.conclusion == "buy"
    assert watch.content == "结构转强"
    assert watch.confidence == 0.7
    assert len(watch_client.calls) == 2
    assert "ignored-pattern" not in watch_client.calls[0][0][1]["content"]
    assert watch_client.calls[0][1] == {"type": "json_object"}

    alert_client = FakeClient(['```json\n{"stop_loss": 9.5, "take_profit": 12.5, "analysis": "守住均线"}\n```'])
    alert = AlertAnalyst(alert_client).analyze(
        {"code": "600519", "name": "贵州茅台", "entry_price": 10},
        pd.DataFrame(concept_rows(days=80)),
    )

    assert alert.suggested_stop_loss == 9.5
    assert alert.suggested_take_profit == 12.5
    assert alert.content == "守住均线"


def test_watch_and_alert_ensemble_consensus_and_degraded_paths():
    class FakeWatchAnalyst:
        def __init__(self, conclusions):
            self.conclusions = list(conclusions)

        def analyze(self, code, name, patterns, klines, user_prompt=""):
            conclusion = self.conclusions.pop(0)
            return WatchAnalysis(code=code, conclusion=conclusion, content=f"{conclusion}理由", analysis_date="2026-06-24")

    strong = WatchEnsemble(FakeWatchAnalyst(["buy", "buy", "buy", "buy", "wait"]), samples=5, rounds_max=1).analyze(
        "600519", "贵州茅台", pd.DataFrame(concept_rows(days=80))
    )
    weak = WatchEnsemble(FakeWatchAnalyst(["buy", "buy", "wait", "wait", "sell"]), samples=5, rounds_max=1).analyze(
        "600519", "贵州茅台", pd.DataFrame(concept_rows(days=80))
    )

    assert strong.conclusion == "buy"
    assert strong.confidence == 0.8
    assert strong.degraded is False
    assert weak.conclusion == "buy"
    assert weak.confidence == 0.4
    assert weak.degraded is True
    assert json.loads(strong.votes)[0]["conclusion"] == "buy"

    class FakeAlertAnalyst:
        def __init__(self, values):
            self.values = list(values)

        def analyze(self, holding, klines, user_prompt=""):
            stop_loss, take_profit = self.values.pop(0)
            return AlertAnalysis(
                code=holding["code"],
                conclusion=f"止损：{stop_loss}；止盈：{take_profit}",
                content="理由",
                analysis_date="2026-06-24",
                suggested_stop_loss=stop_loss,
                suggested_take_profit=take_profit,
            )

    alert = AlertEnsemble(
        FakeAlertAnalyst([(9.9, 12.1), (10.0, 12.0), (10.1, 11.9), (10.2, 12.2), (30.0, 50.0)]),
        samples=5,
        rounds_max=1,
    ).analyze({"code": "600519", "name": "贵州茅台"}, pd.DataFrame(concept_rows(days=80)))

    assert alert.suggested_stop_loss == 10.1
    assert alert.suggested_take_profit == 12.1
    assert alert.degraded is False


def test_ensemble_refills_invalid_votes_before_deciding():
    class FakeWatchAnalyst:
        def __init__(self):
            self.calls = 0

        def analyze(self, code, name, patterns, klines, user_prompt=""):
            self.calls += 1
            if self.calls == 1:
                return WatchAnalysis(code=code, conclusion="wait", content="bad", analysis_date="2026-06-24", degraded=True)
            return WatchAnalysis(code=code, conclusion="buy", content="有效票", analysis_date="2026-06-24")

    watch_analyst = FakeWatchAnalyst()
    watch = WatchEnsemble(watch_analyst, samples=5, rounds_max=1).analyze(
        "600519", "贵州茅台", pd.DataFrame(concept_rows(days=80))
    )

    assert watch_analyst.calls == 6
    assert watch.conclusion == "buy"
    assert watch.confidence == 1.0

    class FakeAlertAnalyst:
        def __init__(self):
            self.calls = 0

        def analyze(self, holding, klines, user_prompt=""):
            self.calls += 1
            if self.calls == 1:
                return AlertAnalysis(holding["code"], "止损：None；止盈：None", "bad", "2026-06-24", degraded=True)
            return AlertAnalysis(
                code=holding["code"],
                conclusion="止损：10；止盈：12",
                content="有效票",
                analysis_date="2026-06-24",
                suggested_stop_loss=10,
                suggested_take_profit=12,
            )

    alert_analyst = FakeAlertAnalyst()
    alert = AlertEnsemble(alert_analyst, samples=5, rounds_max=1).analyze(
        {"code": "600519", "name": "贵州茅台"},
        pd.DataFrame(concept_rows(days=80)),
    )

    assert alert_analyst.calls == 6
    assert alert.confidence == 1.0
    assert alert.degraded is False
