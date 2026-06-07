from __future__ import annotations

import subprocess

from stocktools.infra import cron


def test_set_stocktools_cron_writes_managed_block_and_preserves_existing_cron(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args == ["crontab", "-l"]:
            return subprocess.CompletedProcess(args, 0, "0 9 * * * echo keep\n", "")
        if args == ["crontab", "-"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(cron.subprocess, "run", fake_run)

    cron.set_stocktools_cron(15, 5, 'STOCKTOOLS_HOME="/tmp/work" python3 "/repo/st.py" update')

    written = calls[-1][1]["input"]
    assert "0 9 * * * echo keep" in written
    assert "# StockTools cron begin" in written
    assert '5 15 * * * STOCKTOOLS_HOME="/tmp/work" python3 "/repo/st.py" update' in written
    assert "# StockTools cron end" in written


def test_remove_stocktools_cron_removes_only_managed_block(monkeypatch):
    calls = []
    current = "\n".join(
        [
            "0 9 * * * echo keep",
            "# StockTools cron begin",
            "5 15 * * * STOCKTOOLS_HOME=/tmp python3 st.py update",
            "# StockTools cron end",
            "30 18 * * * echo also-keep",
            "",
        ]
    )

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args == ["crontab", "-l"]:
            return subprocess.CompletedProcess(args, 0, current, "")
        if args == ["crontab", "-"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(cron.subprocess, "run", fake_run)

    removed = cron.remove_stocktools_cron()

    assert removed is True
    written = calls[-1][1]["input"]
    assert "echo keep" in written
    assert "echo also-keep" in written
    assert "StockTools cron begin" not in written


def test_remove_stocktools_cron_reports_false_when_absent(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "0 9 * * * echo keep\n", "")

    monkeypatch.setattr(cron.subprocess, "run", fake_run)

    removed = cron.remove_stocktools_cron()

    assert removed is False
    assert [call[0] for call in calls] == [["crontab", "-l"]]
