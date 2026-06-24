from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", message=r"urllib3 .* doesn't match a supported version!")
import requests


EASTMONEY_CLIST_URLS = [
    "https://82.push2.eastmoney.com/api/qt/clist/get",
    "https://push2.eastmoney.com/api/qt/clist/get",
    "https://40.push2.eastmoney.com/api/qt/clist/get",
]
EASTMONEY_KLINE_URLS = [
    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://82.push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://40.push2his.eastmoney.com/api/qt/stock/kline/get",
]
EASTMONEY_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://quote.eastmoney.com/center/gridlist.html",
}


class EastmoneySession:
    def __init__(self, urls: list[str] | tuple[str, ...], timeout: float = 15.0):
        self.urls = list(urls)
        self.timeout = timeout

    def get_json(self, params: dict[str, object]) -> dict:
        last_error: Exception | None = None
        for url in self.urls:
            session = requests.Session()
            session.trust_env = False
            try:
                response = session.get(url, params=params, timeout=self.timeout, headers=EASTMONEY_HEADERS)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_error = exc
                continue
        raise RuntimeError(f"Eastmoney 请求失败：已尝试直连与备用 host；最后错误：{last_error}") from last_error
