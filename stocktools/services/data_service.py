from __future__ import annotations

import multiprocessing as mp
import queue
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable

from tqdm import tqdm

from stocktools.data.providers.akshare_provider import AkshareProvider
from stocktools.data.providers.baostock_provider import BaostockProvider
from stocktools.data.repos.kline_repo import KlineRepo
from stocktools.services.concept_service import ConceptService

_DATE_CLASS = date


# 单条 baostock 长连接发的查询越多，服务端节流越狠、socket 越易半死（末段会从
# ~20 只/s 塌到 <1 只/s，并伴随 logout failed）。每抓 RELOGIN_EVERY 只就重连一次，
# 把长 session 切成短 session，绕开累积节流。
RELOGIN_EVERY = 400


def _run_shard(db_path: str, shard: list[dict], start: str, end: str, on_each: Callable[[], None] | None) -> dict:
    """逐只抓取一个分片。每个进程独立 baostock 登录（全局 session 是进程级的），
    并按批重连以避免单条连接老化导致的吞吐塌方。"""
    repo = KlineRepo(db_path)
    inserted = 0
    total = 0
    for batch_start in range(0, len(shard), RELOGIN_EVERY):
        batch = shard[batch_start : batch_start + RELOGIN_EVERY]
        with BaostockProvider() as provider:
            for stock in batch:
                total += 1
                try:
                    rows = provider.fetch_history(stock["bs_code"], start, end, stock["name"])
                    inserted += repo.bulk_insert(rows)
                except Exception:
                    pass
                if on_each is not None:
                    on_each()
    return {"stocks": total, "rows": inserted}


def _worker(args: tuple) -> dict:
    """Pool 子进程入口：把每只完成事件投递到进度队列。"""
    # 子进程只通过队列和数据库通信，禁止往终端打印——否则 baostock 的
    # "login success!" 等输出会打断主进程那一行 tqdm 进度条，看起来像多条进度条。
    import os
    import sys

    sys.stdout = sys.stderr = open(os.devnull, "w")
    db_path, shard, start, end, progress_q = args
    on_each = (lambda: progress_q.put(1)) if progress_q is not None else None
    return _run_shard(db_path, shard, start, end, on_each)


def _drain(q) -> int:
    n = 0
    try:
        while True:
            q.get_nowait()
            n += 1
    except queue.Empty:
        pass
    return n


class DataService:
    WORKERS = 4

    def __init__(self, db_path: Path | str, enable_concepts: bool = True, concept_service: ConceptService | None = None):
        self.db_path = db_path
        self.kline_repo = KlineRepo(db_path)
        self.concept_service = concept_service if concept_service is not None else (ConceptService(db_path) if enable_concepts else None)

    def init_history(self) -> dict:
        start = (date.today() - timedelta(days=365)).isoformat()
        end = date.today().isoformat()
        result = self._fetch_per_stock(start, end, progress=True)
        self._attach_concept(result, self._init_concepts(start, end))
        return result

    def update_daily(self, on_fallback: Callable[[str, str], None] | None = None, force: bool = False) -> dict:
        if not force and self._is_intraday_blocked():
            return {"rows": 0, "date": date.today().isoformat(), "status": "blocked_intraday"}
        end = self._latest_possible_trade_date(date.today())
        end_text = end.isoformat()
        latest_date = self.kline_repo.get_latest_date()
        if latest_date and latest_date >= end_text:
            result = {"rows": 0, "date": latest_date, "status": "latest"}
            self._attach_concept(result, self._update_concepts(end_text))
            return result
        # 缺口起点：库里最新日期的次日；空库则退回到只抓 end 当天。
        start_text = (
            (_DATE_CLASS.fromisoformat(latest_date) + timedelta(days=1)).isoformat() if latest_date else end_text
        )
        # akshare 取的是 Eastmoney 实时快照，只代表"最新交易日"，无法回补历史日期。
        # 只有缺口恰好是 end 这一天时才用它（一次请求，最快）。
        if start_text == end_text:
            try:
                rows = AkshareProvider().fetch_daily_all(end)
            except Exception:
                rows = []
            if rows:
                inserted = self.kline_repo.bulk_insert(rows)
                result = {"rows": inserted, "date": rows[0]["date"], "status": "updated"}
                self._attach_concept(result, self._update_concepts(end_text))
                return result
        # 多日缺口，或 akshare 失败：用 baostock 按区间逐只补齐 [start, end]。
        if on_fallback is not None:
            on_fallback(start_text, end_text)
        result = self._fetch_per_stock(start_text, end_text, progress=True)
        actual_date = self.kline_repo.get_latest_date() or end_text
        result = {
            "rows": result["rows"],
            "date": actual_date,
            "status": "fallback",
            "stocks": result["stocks"],
            "start": start_text,
        }
        self._attach_concept(result, self._update_concepts(end_text))
        return result

    def _fetch_per_stock(self, start: str, end: str, progress: bool = False) -> dict:
        db_path = str(self.kline_repo.db_path)
        with BaostockProvider() as provider:
            stocks = provider.list_stocks()
        if not stocks:
            return {"stocks": 0, "rows": 0}
        workers = self.WORKERS
        if workers <= 1 or len(stocks) <= 1:
            bar = tqdm(total=len(stocks), desc="逐只抓取", unit="只", ncols=80) if progress else None
            on_each = (lambda: bar.update(1)) if bar is not None else None
            result = _run_shard(db_path, stocks, start, end, on_each)
            if bar is not None:
                bar.close()
            return result
        return self._fetch_parallel(db_path, stocks, start, end, progress, workers)

    def _fetch_parallel(self, db_path: str, stocks: list[dict], start: str, end: str, progress: bool, workers: int) -> dict:
        ctx = mp.get_context("spawn")
        shards = [stocks[i::workers] for i in range(workers)]
        bar = tqdm(total=len(stocks), desc="逐只抓取", unit="只", ncols=80) if progress else None
        with ctx.Manager() as manager:
            progress_q = manager.Queue() if progress else None
            args = [(db_path, shard, start, end, progress_q) for shard in shards]
            with ctx.Pool(workers) as pool:
                async_result = pool.map_async(_worker, args)
                while not async_result.ready():
                    if bar is not None:
                        bar.update(_drain(progress_q))
                    async_result.wait(0.2)
                if bar is not None:
                    bar.update(_drain(progress_q))
                results = async_result.get()
        if bar is not None:
            bar.close()
        total = sum(r["stocks"] for r in results)
        inserted = sum(r["rows"] for r in results)
        return {"stocks": total, "rows": inserted}

    def _init_concepts(self, start: str, end: str) -> dict:
        if self.concept_service is None:
            return {"status": "skipped"}
        try:
            return self.concept_service.init_history(start, end)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _update_concepts(self, end: str) -> dict:
        if self.concept_service is None:
            return {"status": "skipped"}
        try:
            return self.concept_service.update_daily(end)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    @staticmethod
    def _attach_concept(result: dict, concept: dict) -> None:
        if concept.get("status") != "skipped":
            result["concept"] = concept

    @staticmethod
    def _is_intraday_blocked() -> bool:
        today = date.today()
        now = datetime.now()
        if today != now.date() or today.weekday() >= 5:
            return False
        current = now.time()
        return time(9, 30) <= current <= time(11, 30) or time(13, 0) <= current <= time(15, 0)

    @staticmethod
    def _latest_possible_trade_date(today: date) -> date:
        if today.weekday() == 5:
            return today - timedelta(days=1)
        if today.weekday() == 6:
            return today - timedelta(days=2)
        return today
