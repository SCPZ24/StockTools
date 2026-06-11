from __future__ import annotations

import multiprocessing as mp
import queue
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from tqdm import tqdm

from stocktools.data.providers.akshare_provider import AkshareProvider
from stocktools.data.providers.baostock_provider import BaostockProvider
from stocktools.data.repos.kline_repo import KlineRepo


def _run_shard(db_path: str, shard: list[dict], start: str, end: str, on_each: Callable[[], None] | None) -> dict:
    """逐只抓取一个分片。每个进程独立 baostock 登录（全局 session 是进程级的）。"""
    repo = KlineRepo(db_path)
    inserted = 0
    total = 0
    with BaostockProvider() as provider:
        for stock in shard:
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

    def __init__(self, db_path: Path | str):
        self.kline_repo = KlineRepo(db_path)

    def init_history(self) -> dict:
        start = (date.today() - timedelta(days=365)).isoformat()
        end = date.today().isoformat()
        return self._fetch_per_stock(start, end, progress=True)

    def update_daily(self, on_fallback: Callable[[], None] | None = None) -> dict:
        trade_date = self._latest_possible_trade_date(date.today())
        trade_date_text = trade_date.isoformat()
        latest_date = self.kline_repo.get_latest_date()
        if latest_date and latest_date >= trade_date_text:
            return {"rows": 0, "date": latest_date, "status": "latest"}
        try:
            rows = AkshareProvider().fetch_daily_all(trade_date)
        except Exception:
            rows = []
        if not rows:
            # akshare 行情接口失败或被屏蔽：回退到逐只抓取当前交易日。
            if on_fallback is not None:
                on_fallback()
            result = self._fetch_per_stock(trade_date_text, trade_date_text, progress=True)
            return {"rows": result["rows"], "date": trade_date_text, "status": "fallback", "stocks": result["stocks"]}
        inserted = self.kline_repo.bulk_insert(rows)
        return {"rows": inserted, "date": rows[0]["date"], "status": "updated"}

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

    @staticmethod
    def _latest_possible_trade_date(today: date) -> date:
        if today.weekday() == 5:
            return today - timedelta(days=1)
        if today.weekday() == 6:
            return today - timedelta(days=2)
        return today
