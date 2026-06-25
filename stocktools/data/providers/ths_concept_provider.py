from __future__ import annotations

from collections import OrderedDict
from datetime import date, timedelta
import json
import re
import socket
import threading

import akshare.stock_feature.stock_board_concept_ths as ths_ak
from bs4 import BeautifulSoup
import requests
from urllib3.util import connection as urllib3_connection


THS_PREFIX = "THS"
LIST_URL = "https://q.10jqka.com.cn/gn/detail/code/307822/"
SUMMARY_URL = "http://q.10jqka.com.cn/gn/index/field/addtime/order/desc/page/{page}/ajax/1/"
DETAIL_URL = "https://q.10jqka.com.cn/gn/detail/code/{code}/"
LINE_URL = "https://d.10jqka.com.cn/v4/line/bk_{clid}/01/{year}.js"
THS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/89.0 Safari/537.36",
    "Referer": "http://q.10jqka.com.cn",
}
_IPV4_FORCED = False


def _force_ipv4() -> None:
    global _IPV4_FORCED
    if _IPV4_FORCED:
        return
    urllib3_connection.allowed_gai_family = lambda: socket.AF_INET
    _IPV4_FORCED = True


def _make_v_code() -> str:
    js_code = ths_ak.py_mini_racer.MiniRacer()
    js_code.eval(ths_ak._get_file_content_ths("ths.js"))
    return str(js_code.call("v"))


def _num(value) -> float | None:
    try:
        if value in (None, "", "-", "--"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _day(value: object) -> str | None:
    raw = str(value or "").strip()
    try:
        if re.fullmatch(r"\d{8}", raw):
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8])).isoformat()
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def _normalize_code(value: object) -> str | None:
    raw = str(value or "").strip().upper()
    if raw.startswith(THS_PREFIX):
        raw = raw[len(THS_PREFIX) :]
    if not raw.isdigit():
        return None
    return f"{THS_PREFIX}{raw.zfill(6)}"


class ThsHttpClient:
    def __init__(self, session: requests.Session | None = None, timeout: float = 10.0, v_code: str | None = None):
        self.session = session
        if self.session is not None:
            self.session.trust_env = False
        self.timeout = timeout
        self.v_code = v_code or _make_v_code()

    def get_text(self, url: str, host: str | None = None) -> str:
        headers = dict(THS_HEADERS)
        headers["Cookie"] = f"v={self.v_code}"
        if host:
            headers["Host"] = host
        if self.session is not None:
            return self._get_text_with_session(self.session, url, headers)
        last_error: Exception | None = None
        for trust_env in (False, True):
            session = requests.Session()
            session.trust_env = trust_env
            if not trust_env:
                _force_ipv4()
            try:
                return self._get_text_with_session(session, url, headers)
            except Exception as exc:
                last_error = exc
            finally:
                session.close()
        raise last_error or RuntimeError(f"同花顺请求失败：{url}")

    def _get_text_with_session(self, session: requests.Session, url: str, headers: dict[str, str]) -> str:
        response = session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        if not getattr(response, "encoding", None) or str(response.encoding).lower() == "iso-8859-1":
            response.encoding = "gbk"
        return response.text


class ThsConceptProvider:
    """同花顺概念板块数据源。

    同花顺没有一次性实时涨跌幅列表；列表只提供名称和代码，日涨幅由日 K
    收盘价按相邻交易日计算。
    """

    deactivate_missing = False

    def __init__(self, client: ThsHttpClient | None = None):
        self.client = client or ThsHttpClient()
        self._name_by_code: dict[str, str] = {}
        self._clid_by_code: dict[str, str] = {}
        self._clid_lock = threading.Lock()

    def can_handle(self, code: str) -> bool:
        return _normalize_code(code) is not None

    def fetch_concepts(self) -> list[dict]:
        concepts: OrderedDict[str, str] = OrderedDict()
        self._merge_concepts(concepts, self.client.get_text(LIST_URL))
        try:
            first_page = self.client.get_text(SUMMARY_URL.format(page=1))
            self._merge_concepts(concepts, first_page)
            for page in range(2, self._summary_page_count(first_page) + 1):
                self._merge_concepts(concepts, self.client.get_text(SUMMARY_URL.format(page=page)))
        except Exception:
            if not concepts:
                raise
        self._name_by_code = dict(concepts)
        return [{"code": code, "name": name} for code, name in concepts.items()]

    def fetch_kline(self, code: str, start: str, end: str) -> list[dict]:
        normalized = _normalize_code(code)
        if normalized is None:
            raise ValueError(f"同花顺概念代码无效：{code}")
        start_day = date.fromisoformat(start)
        end_day = date.fromisoformat(end)
        request_start = start_day - timedelta(days=10)
        clid = self._resolve_clid(normalized)
        records: list[list[str]] = []
        for year in range(request_start.year, end_day.year + 1):
            try:
                text = self.client.get_text(LINE_URL.format(clid=clid, year=year), host="d.10jqka.com.cn")
            except Exception:
                continue
            records.extend(self._parse_line_records(text))
        rows = []
        previous_close: float | None = None
        for parts in sorted(records, key=lambda item: item[0]):
            if len(parts) < 7:
                continue
            day = _day(parts[0])
            open_ = _num(parts[1])
            high = _num(parts[2])
            low = _num(parts[3])
            close = _num(parts[4])
            volume = _num(parts[5])
            amount = _num(parts[6])
            if day is None or any(v is None for v in (open_, high, low, close, volume, amount)):
                continue
            pct_chg = 0.0
            if previous_close and previous_close > 0:
                pct_chg = round((float(close) - previous_close) / previous_close * 100, 2)
            if start <= day <= end:
                rows.append(
                    {
                        "code": normalized,
                        "date": day,
                        "open": float(open_),
                        "close": float(close),
                        "high": float(high),
                        "low": float(low),
                        "volume": float(volume),
                        "amount": float(amount),
                        "pct_chg": pct_chg,
                        "turnover": 0.0,
                    }
                )
            previous_close = float(close)
        return rows

    def _merge_concepts(self, concepts: OrderedDict[str, str], html: str) -> None:
        for name, code in self._parse_concept_links(html):
            concepts[code] = name

    @staticmethod
    def _parse_concept_links(html: str) -> list[tuple[str, str]]:
        soup = BeautifulSoup(html, features="lxml")
        root = soup.find(name="div", attrs={"class": "cate_inner"}) or soup
        rows = []
        for item in root.find_all(name="a"):
            href = item.get("href") or ""
            match = re.search(r"/gn/detail/code/(\d+)/?", href)
            name = item.get_text(strip=True)
            code = _normalize_code(match.group(1) if match else None)
            if code and name:
                rows.append((name, code))
        return rows

    @staticmethod
    def _summary_page_count(html: str) -> int:
        soup = BeautifulSoup(html, features="lxml")
        info = soup.find(name="span", attrs={"class": "page_info"})
        if not info:
            return 1
        try:
            return int(info.get_text(strip=True).split("/")[-1])
        except (TypeError, ValueError):
            return 1

    def _resolve_clid(self, code: str) -> str:
        raw = code.removeprefix(THS_PREFIX)
        with self._clid_lock:
            if code in self._clid_by_code:
                return self._clid_by_code[code]
        html = self.client.get_text(DETAIL_URL.format(code=raw))
        soup = BeautifulSoup(html, features="lxml")
        item = soup.find(name="input", attrs={"id": "clid"})
        if item is None or not item.get("value"):
            raise ValueError(f"无法解析同花顺概念内部代码：{code}")
        clid = str(item["value"]).strip()
        with self._clid_lock:
            self._clid_by_code[code] = clid
        return clid

    @staticmethod
    def _parse_line_records(text: str) -> list[list[str]]:
        match = re.search(r"\((\{.*\})\)\s*$", text, re.S)
        if not match:
            return []
        payload = json.loads(match.group(1))
        data = str(payload.get("data") or "")
        return [line.split(",") for line in data.split(";") if line]
