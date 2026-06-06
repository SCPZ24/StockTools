"""baostock 数据源 — 整个扫描期间只维护一个会话"""

import baostock as bs
import pandas as pd
from datetime import datetime, timedelta

from config import LOOKBACK_YEARS


class BaostockSession:
    """上下文管理器：进入时 login，退出时 logout，中间所有请求复用同一连接。"""

    def __enter__(self):
        result = bs.login()
        if result.error_code != "0":
            raise RuntimeError(f"baostock login failed: {result.error_msg}")
        return self

    def __exit__(self, *exc):
        bs.logout()

    # ── 行情数据 ──────────────────────────────────────

    def query_weekly(self, code: str, lookback_years: int = LOOKBACK_YEARS) -> pd.DataFrame | None:
        return self._query_kline(code, "w", lookback_years)

    def query_daily(self, code: str, lookback_years: int = LOOKBACK_YEARS) -> pd.DataFrame | None:
        return self._query_kline(code, "d", lookback_years)

    def _query_kline(self, code: str, freq: str, lookback_years: int) -> pd.DataFrame | None:
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=lookback_years * 365)).strftime("%Y-%m-%d")
        try:
            rs = bs.query_history_k_data_plus(
                code,
                "date,open,high,low,close,volume",
                start_date=start, end_date=end,
                frequency=freq, adjustflag="2",
            )
            return self._to_dataframe(rs)
        except Exception:
            return None

    # ── 指数成分 ──────────────────────────────────────

    def query_hs300(self) -> set[str]:
        data = bs.query_hs300_stocks().get_data()
        return set(data["code"].tolist()) if data is not None and len(data) > 0 else set()

    def query_zz500(self) -> set[str]:
        data = bs.query_zz500_stocks().get_data()
        return set(data["code"].tolist()) if data is not None and len(data) > 0 else set()

    def query_all_stocks(self) -> pd.DataFrame:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        return bs.query_all_stock(day=yesterday).get_data()

    # ── 内部工具 ──────────────────────────────────────

    @staticmethod
    def _to_dataframe(rs) -> pd.DataFrame | None:
        data = rs.get_data()
        if data is None or len(data) == 0:
            return None
        for col in ("open", "high", "low", "close", "volume"):
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")
        if "date" in data.columns:
            data["date"] = pd.to_datetime(data["date"])
        data = data.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
        return data if len(data) > 0 else None
