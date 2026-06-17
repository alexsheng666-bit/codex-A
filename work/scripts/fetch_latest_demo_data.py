#!/usr/bin/env python3
"""Fetch a recent A-share snapshot for dashboard screening.

Data source: Eastmoney public quote API. This script is for research/demo use
only and does not provide investment advice.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import signal
import time
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from rules_config import DEFAULT_RULES, DEFAULT_THEME_KEYWORDS, load_rules, screening_from_rules


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "01_原始资料" / "market_data" / "raw_csv" / "latest_market_data.csv"
UNIVERSE_CACHE = ROOT / "work" / "cache" / "stock_universe.csv"
HOSTS = [
    "82.push2.eastmoney.com",
    "push2.eastmoney.com",
    "48.push2.eastmoney.com",
    "32.push2.eastmoney.com",
]
INCLUDE_PREFIXES = ("600", "601", "603", "605", "000", "001", "002", "003")
EXCLUDE_PREFIXES = ("300", "301", "688", "8", "4", "9")
FIELDS = "f12,f14,f13,f3,f2,f4,f5,f6,f7,f8,f10,f15,f16,f17,f18,f20,f21,f100,f124"
MIN_FULL_SOURCE_ROWS = 800
MIN_EASTMONEY_ROWS = MIN_FULL_SOURCE_ROWS
MIN_UNIVERSE_FALLBACK_ROWS = 80
SINA_BATCH_SIZE = 80
THS_TIMEOUT_SECONDS = 25
AKSHARE_TIMEOUT_SECONDS = 25
EASTMONEY_TIMEOUT_SECONDS = 50
THS_URL = "https://q.10jqka.com.cn/index/index/board/hs/field/zdf/order/desc/page/{page}/ajax/1/"
THS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://q.10jqka.com.cn/",
    "X-Requested-With": "XMLHttpRequest",
}
T = TypeVar("T")

THEME_KEYWORDS = {theme: list(keywords) for theme, keywords in DEFAULT_THEME_KEYWORDS.items()}

SINA_FOCUS_STOCKS = [
    ("sh600900", "电力", "水电;绿电"),
    ("sh601985", "电力", "核电;绿电"),
    ("sh600795", "电力", "火电;绿电"),
    ("sh600011", "电力", "火电"),
    ("sh600027", "电力", "火电"),
    ("sz000539", "电力", "火电;绿电"),
    ("sz000600", "电力", "火电"),
    ("sz001896", "电力", "电力"),
    ("sh600100", "科技", "人工智能;算力;数据中心"),
    ("sz000063", "科技", "通信;算力;科技"),
    ("sz000066", "科技", "信创;科技"),
    ("sz002230", "科技", "人工智能;软件"),
    ("sz000977", "科技", "服务器;算力;数据中心"),
    ("sz002415", "科技", "人工智能;安防;科技"),
    ("sz000547", "商业航天", "航天;卫星互联网;北斗导航"),
    ("sh600879", "商业航天", "航天;卫星"),
    ("sh600118", "商业航天", "卫星;航天"),
    ("sh600501", "商业航天", "商业航天;航天"),
    ("sz002465", "商业航天", "卫星通信;北斗导航"),
    ("sz002151", "商业航天", "北斗导航;卫星"),
    ("sh600584", "半导体", "半导体;封测;芯片"),
    ("sh600703", "半导体", "半导体;芯片"),
    ("sz002049", "半导体", "半导体;芯片"),
    ("sz002371", "半导体", "半导体;设备;芯片"),
    ("sz002185", "半导体", "半导体;封测"),
    ("sh600460", "半导体", "半导体;芯片"),
    ("sh603501", "半导体", "半导体;芯片"),
    ("sz002463", "PCB", "PCB;高速板;AI服务器"),
    ("sz002384", "PCB", "PCB;消费电子"),
    ("sz002916", "PCB", "PCB;封装基板"),
    ("sh603228", "PCB", "PCB;印制电路板"),
    ("sz002938", "PCB", "PCB;消费电子"),
]


class ProviderTimeoutError(TimeoutError):
    pass


def run_with_timeout(label: str, seconds: int, func: Callable[..., T], *args: object, **kwargs: object) -> T:
    def timeout_handler(signum: int, frame: object) -> None:
        raise ProviderTimeoutError(f"{label} timed out after {seconds}s")

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, 0)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return func(*args, **kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])


def apply_rules_config(rules: Dict[str, object]) -> None:
    global THEME_KEYWORDS
    config = screening_from_rules(rules)
    THEME_KEYWORDS = {theme: list(keywords) for theme, keywords in config["theme_keywords"].items()}


def request_json(host: str, page: int, page_size: int) -> Dict[str, object]:
    query = {
        "pn": page,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": "m:1+t:2,m:0+t:6",
        "fields": FIELDS,
    }
    url = f"https://{host}/api/qt/clist/get?{urlencode(query)}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
    with urlopen(req, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_page(page: int, page_size: int, retries: int = 1) -> Dict[str, object]:
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        for host in HOSTS:
            try:
                return request_json(host, page, page_size)
            except (HTTPError, URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
                time.sleep(0.25 + attempt * 0.25)
    raise RuntimeError(f"Failed to fetch page {page}: {last_error}")


def fetch_all(page_size: int = 200, max_pages: int = 30, min_rows: int = MIN_EASTMONEY_ROWS) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    total = None
    for page in range(1, max_pages + 1):
        try:
            data = fetch_page(page, page_size)
        except Exception:
            if len(rows) >= min_rows:
                print(f"Eastmoney stopped at page {page}; using partial snapshot with {len(rows)} rows")
                break
            raise
        body = data.get("data") or {}
        page_rows = body.get("diff") or []
        if not isinstance(page_rows, list) or not page_rows:
            break
        rows.extend(page_rows)
        total = int(body.get("total") or 0)
        print(f"Fetched page {page}: {len(page_rows)} rows, total so far {len(rows)}")
        if total and len(rows) >= total:
            break
        time.sleep(0.08)
    return rows


def fetch_akshare_all() -> List[Dict[str, object]]:
    import akshare as ak  # type: ignore

    df = ak.stock_zh_a_spot_em()
    rows = df.to_dict("records")
    trade_date = datetime.now().strftime("%Y-%m-%d")
    converted = []
    for row in rows:
        code = clean_code(row.get("代码"))
        name = str(row.get("名称") or "")
        if not is_main_board(code, name):
            continue
        close = safe_float(row.get("最新价"))
        pct_change = safe_float(row.get("涨跌幅"))
        high = safe_float(row.get("最高"), close)
        low = safe_float(row.get("最低"), close)
        open_price = safe_float(row.get("今开"), close)
        pre_close = safe_float(row.get("昨收"), close)
        volume_ratio = safe_float(row.get("量比"), 1.0)
        turnover_rate = safe_float(row.get("换手率"))
        amount = safe_float(row.get("成交额"))
        volume = safe_float(row.get("成交量"))
        amplitude = safe_float(row.get("振幅"))
        tags = theme_tags(name, "")
        close_position = close / high * 100 if high else 0
        ma5 = round(close * 0.985, 2)
        ma10 = round(close * 0.97, 2)
        ma20 = round(close * 0.94, 2)
        converted.append(
            {
                "trade_date": trade_date,
                "stock_code": code,
                "stock_name": name,
                "board": board_for(code),
                "market": market_for(code),
                "industry": "",
                "concepts": ";".join(tags),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "pre_close": pre_close,
                "pct_change": pct_change,
                "turnover_amount": int(amount),
                "turnover_rate": turnover_rate,
                "volume": int(volume),
                "volume_ratio": volume_ratio,
                "amplitude": amplitude,
                "market_cap": int(safe_float(row.get("总市值"))),
                "float_market_cap": int(safe_float(row.get("流通市值"))),
                "limit_up_status": yes_no(pct_change >= 9.8),
                "first_limit_up_time": "",
                "last_limit_up_time": "",
                "limit_up_break_count": 0,
                "consecutive_limit_up_count": 1 if pct_change >= 9.8 else 0,
                "tail_rise_pct": max(0.0, round(pct_change * 0.35, 2)),
                "tail_volume_ratio": max(volume_ratio, 1.0),
                "close_position_pct": round(close_position, 1),
                "above_vwap_most_day": yes_no(pct_change > 0 and close >= open_price),
                "stepwise_rise_after_1430": yes_no(pct_change >= 2 and close_position >= 92 and volume_ratio >= 1.1),
                "break_intraday_high": yes_no(close_position >= 96),
                "break_key_resistance": yes_no(pct_change >= 3 and volume_ratio >= 1.2),
                "tail_pullback_holds": yes_no(close >= open_price or close_position >= 92),
                "ma5": ma5,
                "ma10": ma10,
                "ma20": ma20,
                "ma_alignment_up": yes_no(close > ma5 > ma10 > ma20),
                "pullback_to_ma10_or_ma20": "否",
                "close_above_ma5": yes_no(close > ma5),
                "recent_volume_rank_low": "否",
                "close_gt_open": yes_no(close > open_price),
                "kdj_low_turn_up": "否",
                "rsi_low_turn_up": "否",
                "theme_limit_up_count": 3 if tags else 0,
                "theme_rank": 2 if tags else 9,
                "theme_tail_reflow": yes_no(bool(tags) and pct_change >= 2 and volume_ratio >= 1.1),
                "theme_leader_auction": "",
                "manual_note": "AKShare 全沪深主板快照；尾盘字段为日内快照近似值",
                "data_source": "akshare_stock_zh_a_spot_em",
                "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return converted


def fetch_ths_page(page: int) -> List[Dict[str, object]]:
    import pandas as pd  # type: ignore

    url = THS_URL.format(page=page)
    req = Request(url, headers=THS_HEADERS)
    with urlopen(req, timeout=18) as response:
        html_text = response.read().decode("gbk", errors="replace")

    tables = pd.read_html(StringIO(html_text))
    if not tables:
        return []
    table = tables[0]
    if table.empty:
        return []
    return table.to_dict("records")


def fetch_ths_all(max_pages: int = 80, min_rows: int = 800) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for page in range(1, max_pages + 1):
        try:
            page_rows = fetch_ths_page(page)
        except HTTPError as exc:
            if rows:
                print(f"THS stopped at page {page}: HTTP {exc.code}")
                break
            raise
        if not page_rows:
            break
        converted = [convert_ths_row(row) for row in page_rows]
        rows.extend(row for row in converted if row)
        print(f"Fetched THS page {page}: {len(page_rows)} rows, eligible so far {len(rows)}")
        time.sleep(0.45)

    if len(rows) < min_rows:
        update_universe_cache(rows, "ths_q_hs_snapshot_partial")
        raise RuntimeError(f"THS returned only {len(rows)} eligible rows; fallback required")
    update_universe_cache(rows, "ths_q_hs_snapshot")
    return rows


def get_alias(row: Dict[str, object], *aliases: str) -> object:
    normalized = {str(key).replace(" ", ""): value for key, value in row.items()}
    for alias in aliases:
        key = alias.replace(" ", "")
        if key in normalized:
            return normalized[key]
    for key, value in normalized.items():
        if any(alias.replace(" ", "") in key for alias in aliases):
            return value
    return ""


def parse_cn_number(value: object, default: float = 0.0) -> float:
    if value in (None, "-", "--", ""):
        return default
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text:
        return default
    multiplier = 1.0
    if text.endswith("万亿"):
        multiplier = 1_000_000_000_000.0
        text = text[:-2]
    elif text.endswith("亿"):
        multiplier = 100_000_000.0
        text = text[:-1]
    elif text.endswith("万"):
        multiplier = 10_000.0
        text = text[:-1]
    try:
        number = float(text) * multiplier
        return number if math.isfinite(number) else default
    except ValueError:
        return default


def convert_ths_row(row: Dict[str, object]) -> Optional[Dict[str, object]]:
    code = clean_code(get_alias(row, "代码"))
    name = str(get_alias(row, "名称") or "").strip()
    if not is_main_board(code, name):
        return None

    trade_date = datetime.now().strftime("%Y-%m-%d")
    close = parse_cn_number(get_alias(row, "现价"))
    pct_change = parse_cn_number(get_alias(row, "涨跌幅"))
    turnover_rate = parse_cn_number(get_alias(row, "换手"))
    volume_ratio = parse_cn_number(get_alias(row, "量比"), 1.0)
    amplitude = parse_cn_number(get_alias(row, "振幅"))
    amount = parse_cn_number(get_alias(row, "成交额"))
    float_market_cap = parse_cn_number(get_alias(row, "流通市值"))
    pre_close = round(close / (1 + pct_change / 100), 2) if close and pct_change > -99 else close
    high = round(close * (1 + max(amplitude, 0) / 200), 2) if close else 0
    low = round(close * (1 - max(amplitude, 0) / 200), 2) if close else 0
    open_price = pre_close
    tags = theme_tags(name, "")
    close_position = close / high * 100 if high else 0
    limit_up = pct_change >= 9.8
    ma5 = round(close * 0.985, 2)
    ma10 = round(close * 0.97, 2)
    ma20 = round(close * 0.94, 2)
    theme_limit_up_count = 3 if any(tag in tags for tag in ("半导体", "PCB", "商业航天", "科技")) else 2 if tags else 0
    theme_rank = 1 if any(tag in tags for tag in ("半导体", "PCB")) else 2 if tags else 9

    return {
        "trade_date": trade_date,
        "stock_code": code,
        "stock_name": name,
        "board": board_for(code),
        "market": market_for(code),
        "industry": "",
        "concepts": ";".join(tags),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "pre_close": pre_close,
        "pct_change": pct_change,
        "turnover_amount": int(amount),
        "turnover_rate": turnover_rate,
        "volume": 0,
        "volume_ratio": volume_ratio,
        "amplitude": amplitude,
        "market_cap": int(float_market_cap),
        "float_market_cap": int(float_market_cap),
        "limit_up_status": yes_no(limit_up),
        "first_limit_up_time": "",
        "last_limit_up_time": "",
        "limit_up_break_count": 0,
        "consecutive_limit_up_count": 1 if limit_up else 0,
        "tail_rise_pct": max(0.0, round(pct_change * 0.35, 2)),
        "tail_volume_ratio": max(volume_ratio, 1.0),
        "close_position_pct": round(close_position, 1),
        "above_vwap_most_day": yes_no(pct_change > 0 and close >= open_price),
        "stepwise_rise_after_1430": yes_no(pct_change >= 2 and close_position >= 92 and volume_ratio >= 1.1),
        "break_intraday_high": yes_no(close_position >= 96),
        "break_key_resistance": yes_no(pct_change >= 3 and volume_ratio >= 1.2),
        "tail_pullback_holds": yes_no(close >= open_price or close_position >= 92),
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma_alignment_up": yes_no(close > ma5 > ma10 > ma20),
        "pullback_to_ma10_or_ma20": "否",
        "close_above_ma5": yes_no(close > ma5),
        "recent_volume_rank_low": "否",
        "close_gt_open": yes_no(close > open_price),
        "kdj_low_turn_up": "否",
        "rsi_low_turn_up": "否",
        "theme_limit_up_count": theme_limit_up_count,
        "theme_rank": theme_rank,
        "theme_tail_reflow": yes_no(pct_change >= 2 and volume_ratio >= 1.1),
        "theme_leader_auction": "",
        "manual_note": "同花顺沪深行情列表；尾盘字段为日内快照近似值，开高低为列表字段不足时的估算",
        "data_source": "ths_q_hs_snapshot",
        "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def clean_code(value: object) -> str:
    code = "".join(ch for ch in str(value or "") if ch.isdigit())
    return code.zfill(6)[-6:] if code else ""


def is_main_board(code: str, name: str) -> bool:
    upper_name = name.upper()
    if not code.startswith(INCLUDE_PREFIXES):
        return False
    if code.startswith(EXCLUDE_PREFIXES):
        return False
    if "ST" in upper_name or "*" in upper_name or "退" in name:
        return False
    return True


def board_for(code: str) -> str:
    if code.startswith(("600", "601", "603", "605")):
        return "沪主板"
    return "深主板"


def market_for(code: str) -> str:
    if code.startswith(("600", "601", "603", "605")):
        return "SH"
    return "SZ"


def theme_tags(name: str, industry: str) -> List[str]:
    text = f"{name} {industry}".upper()
    tags = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword.upper() in text for keyword in keywords):
            tags.append(theme)
    return tags


def safe_float(value: object, default: float = 0.0) -> float:
    if value in (None, "-", ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def trade_date_from_rows(rows: Iterable[Dict[str, object]]) -> str:
    timestamps = [int(row.get("f124") or 0) for row in rows if row.get("f124")]
    if not timestamps:
        return datetime.now().strftime("%Y-%m-%d")
    return datetime.fromtimestamp(max(timestamps)).strftime("%Y-%m-%d")


def yes_no(value: bool) -> str:
    return "是" if value else "否"


def convert_row(row: Dict[str, object], trade_date: str) -> Optional[Dict[str, object]]:
    code = clean_code(row.get("f12"))
    name = str(row.get("f14") or "").strip()
    if not is_main_board(code, name):
        return None

    industry = str(row.get("f100") or "").strip()
    tags = theme_tags(name, industry)

    close = safe_float(row.get("f2"))
    pct_change = safe_float(row.get("f3"))
    high = safe_float(row.get("f15"), close)
    low = safe_float(row.get("f16"), close)
    open_price = safe_float(row.get("f17"), close)
    pre_close = safe_float(row.get("f18"), close)
    volume_ratio = safe_float(row.get("f10"), 1.0)
    turnover_rate = safe_float(row.get("f8"))
    amount = safe_float(row.get("f6"))
    volume = safe_float(row.get("f5"))
    amplitude = safe_float(row.get("f7"))
    close_position = close / high * 100 if high else 0
    limit_up = pct_change >= 9.8

    # These are daily-snapshot approximations for demo purposes. Minute data can
    # replace them later.
    tail_volume_ratio = max(volume_ratio, 1.0)
    stepwise = pct_change >= 2 and close_position >= 92 and volume_ratio >= 1.1
    break_high = close_position >= 96
    break_resistance = pct_change >= 3 and volume_ratio >= 1.2
    pullback_holds = close >= open_price or close_position >= 92
    ma5 = round(close * 0.985, 2)
    ma10 = round(close * 0.97, 2)
    ma20 = round(close * 0.94, 2)
    theme_limit_up_count = 3 if any(tag in tags for tag in ("半导体", "PCB", "商业航天", "科技")) else 2 if tags else 0
    theme_rank = 1 if any(tag in tags for tag in ("半导体", "PCB")) else 2 if tags else 9

    return {
        "trade_date": trade_date,
        "stock_code": code,
        "stock_name": name,
        "board": board_for(code),
        "market": market_for(code),
        "industry": industry,
        "concepts": ";".join(tags),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "pre_close": pre_close,
        "pct_change": pct_change,
        "turnover_amount": int(amount),
        "turnover_rate": turnover_rate,
        "volume": int(volume),
        "volume_ratio": volume_ratio,
        "amplitude": amplitude,
        "market_cap": int(safe_float(row.get("f20"))),
        "float_market_cap": int(safe_float(row.get("f21"))),
        "limit_up_status": yes_no(limit_up),
        "first_limit_up_time": "",
        "last_limit_up_time": "",
        "limit_up_break_count": 0,
        "consecutive_limit_up_count": 1 if limit_up else 0,
        "tail_rise_pct": max(0.0, round(pct_change * 0.35, 2)),
        "tail_volume_ratio": tail_volume_ratio,
        "close_position_pct": round(close_position, 1),
        "above_vwap_most_day": yes_no(pct_change > 0 and close >= open_price),
        "stepwise_rise_after_1430": yes_no(stepwise),
        "break_intraday_high": yes_no(break_high),
        "break_key_resistance": yes_no(break_resistance),
        "tail_pullback_holds": yes_no(pullback_holds),
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma_alignment_up": yes_no(close > ma5 > ma10 > ma20),
        "pullback_to_ma10_or_ma20": "否",
        "close_above_ma5": yes_no(close > ma5),
        "recent_volume_rank_low": "否",
        "close_gt_open": yes_no(close > open_price),
        "kdj_low_turn_up": "否",
        "rsi_low_turn_up": "否",
        "theme_limit_up_count": theme_limit_up_count,
        "theme_rank": theme_rank,
        "theme_tail_reflow": yes_no(pct_change >= 2 and volume_ratio >= 1.1),
        "theme_leader_auction": "",
        "manual_note": "东方财富全沪深主板快照；尾盘字段为日内快照近似值",
        "data_source": "eastmoney_push2_snapshot",
        "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def select_demo_rows(rows: List[Dict[str, object]], max_rows: int) -> List[Dict[str, object]]:
    converted = [row for row in rows if row is not None]
    converted.sort(
        key=lambda row: (
            bool(str(row.get("concepts", "")).strip()),
            len([item for item in str(row.get("concepts", "")).split(";") if item]),
            safe_float(row.get("pct_change")),
            safe_float(row.get("turnover_amount")),
        ),
        reverse=True,
    )
    if max_rows <= 0:
        return converted
    selected: List[Dict[str, object]] = []
    seen_themes = set()
    for row in converted:
        themes = set(str(row.get("concepts", "")).split(";"))
        if themes - seen_themes:
            selected.append(row)
            seen_themes.update(themes)
        if len(selected) >= max_rows:
            return selected
    for row in converted:
        if row not in selected:
            selected.append(row)
        if len(selected) >= max_rows:
            break
    return selected


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise SystemExit("No rows to write.")
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_snapshot_csv(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return [dict(row) for row in csv.DictReader(file)]


def read_universe_cache(path: Path = UNIVERSE_CACHE) -> Dict[str, Dict[str, object]]:
    if not path.exists():
        return {}
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return {clean_code(row.get("stock_code")): dict(row) for row in csv.DictReader(file) if row.get("stock_code")}


def write_universe_cache(cache: Dict[str, Dict[str, object]], path: Path = UNIVERSE_CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "stock_code",
        "stock_name",
        "board",
        "market",
        "industry",
        "concepts",
        "first_seen",
        "last_seen",
        "data_source",
    ]
    rows = sorted(cache.values(), key=lambda row: str(row.get("stock_code", "")))
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in fieldnames} for row in rows])


def update_universe_cache(rows: Iterable[Dict[str, object]], source: str) -> int:
    cache = read_universe_cache()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    changed = 0
    for row in rows:
        code = clean_code(row.get("stock_code"))
        name = str(row.get("stock_name") or "").strip()
        if not is_main_board(code, name):
            continue
        existing = cache.get(code, {})
        industry = str(row.get("industry") or existing.get("industry") or "").strip()
        concepts = str(row.get("concepts") or existing.get("concepts") or "").strip()
        cache[code] = {
            "stock_code": code,
            "stock_name": name or existing.get("stock_name", ""),
            "board": board_for(code),
            "market": market_for(code),
            "industry": industry,
            "concepts": concepts,
            "first_seen": existing.get("first_seen") or now,
            "last_seen": now,
            "data_source": source,
        }
        changed += 1
    if changed:
        write_universe_cache(cache)
        print(f"Updated local stock universe: {len(cache)} rows")
    return changed


def universe_to_sina_symbols(path: Path = UNIVERSE_CACHE) -> List[tuple[str, str, str]]:
    cache = read_universe_cache(path)
    symbols: List[tuple[str, str, str]] = []
    for row in cache.values():
        code = clean_code(row.get("stock_code"))
        name = str(row.get("stock_name") or "")
        if not is_main_board(code, name):
            continue
        prefix = "sh" if market_for(code) == "SH" else "sz"
        industry = str(row.get("industry") or "")
        concepts = str(row.get("concepts") or "")
        symbols.append((f"{prefix}{code}", industry, concepts))
    return sorted(symbols)


def fetch_sina_focus() -> List[Dict[str, object]]:
    return fetch_sina_symbols(
        SINA_FOCUS_STOCKS,
        data_source="sina_hq_focus_snapshot",
        manual_note="新浪行情最近交易日演示数据；尾盘字段为日线快照近似值",
    )


def fetch_sina_universe() -> List[Dict[str, object]]:
    symbols = universe_to_sina_symbols()
    if len(symbols) < MIN_UNIVERSE_FALLBACK_ROWS:
        raise RuntimeError(f"Local universe has only {len(symbols)} rows")
    return fetch_sina_symbols(
        symbols,
        data_source="sina_hq_universe_snapshot",
        manual_note="新浪行情本地股票池快照；股票池来自历史成功采集，尾盘字段为日线快照近似值",
    )


def fetch_sina_symbols(
    symbols: List[tuple[str, str, str]],
    data_source: str,
    manual_note: str,
) -> List[Dict[str, object]]:
    meta = {symbol[-6:]: (industry, concepts) for symbol, industry, concepts in symbols}
    rows: List[Dict[str, object]] = []
    latest_date = ""
    for index in range(0, len(symbols), SINA_BATCH_SIZE):
        batch = symbols[index : index + SINA_BATCH_SIZE]
        query = ",".join(symbol for symbol, _, _ in batch)
        url = f"https://hq.sinajs.cn/list={query}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"})
        with urlopen(req, timeout=18) as response:
            text = response.read().decode("gbk", errors="replace")
        time.sleep(0.12)
        for line in text.splitlines():
            if '="' not in line:
                continue
            left, raw = line.split('="', 1)
            symbol = left.rsplit("_", 1)[-1]
            code = symbol[-6:]
            values = raw.rstrip('";').split(",")
            if len(values) < 32 or not values[0]:
                continue
            row = convert_sina_values(code, values, meta, data_source, manual_note)
            if row:
                latest_date = max(latest_date, str(row.get("trade_date") or ""))
                rows.append(row)
    rows.sort(key=lambda row: (row.get("trade_date") == latest_date, safe_float(row.get("pct_change"))), reverse=True)
    return rows


def convert_sina_values(
    code: str,
    values: List[str],
    meta: Dict[str, tuple[str, str]],
    data_source: str,
    manual_note: str,
) -> Optional[Dict[str, object]]:
        name = values[0]
        if not is_main_board(code, name):
            return None
        open_price = safe_float(values[1])
        pre_close = safe_float(values[2])
        close = safe_float(values[3])
        high = safe_float(values[4], close)
        low = safe_float(values[5], close)
        volume = safe_float(values[8])
        amount = safe_float(values[9])
        date = values[30] if len(values) > 30 else datetime.now().strftime("%Y-%m-%d")

        if close <= 0 or pre_close <= 0:
            return None
        pct_change = round((close - pre_close) / pre_close * 100, 2)
        amplitude = round((high - low) / pre_close * 100, 2) if pre_close else 0
        close_position = close / high * 100 if high else 0
        industry, concepts = meta.get(code, ("", ""))
        turnover_rate = 3.8 if amount >= 1_000_000_000 else 2.0 if amount >= 300_000_000 else 0.8
        volume_ratio = 1.8 if amount >= 1_000_000_000 and pct_change > 2 else 1.35 if pct_change > 1 else 1.0
        tags = theme_tags(name, f"{industry};{concepts}") or [industry]
        limit_up = pct_change >= 9.7
        ma5 = round(close * 0.985, 2)
        ma10 = round(close * 0.97, 2)
        ma20 = round(close * 0.94, 2)
        theme_limit_up_count = 3 if industry in {"科技", "商业航天", "半导体", "PCB"} else 2
        theme_rank = 1 if industry in {"PCB", "半导体"} else 2

        return {
            "trade_date": date,
            "stock_code": code,
            "stock_name": name,
            "board": board_for(code),
            "market": market_for(code),
            "industry": industry,
            "concepts": concepts,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "pre_close": pre_close,
            "pct_change": pct_change,
            "turnover_amount": int(amount),
            "turnover_rate": turnover_rate,
            "volume": int(volume),
            "volume_ratio": volume_ratio,
            "amplitude": amplitude,
            "market_cap": 0,
            "float_market_cap": 0,
            "limit_up_status": yes_no(limit_up),
            "first_limit_up_time": "",
            "last_limit_up_time": "",
            "limit_up_break_count": 0,
            "consecutive_limit_up_count": 1 if limit_up else 0,
            "tail_rise_pct": max(0.0, round(pct_change * 0.35, 2)),
            "tail_volume_ratio": volume_ratio,
            "close_position_pct": round(close_position, 1),
            "above_vwap_most_day": yes_no(pct_change > 0 and close >= open_price),
            "stepwise_rise_after_1430": yes_no(pct_change >= 2 and close_position >= 92),
            "break_intraday_high": yes_no(close_position >= 96),
            "break_key_resistance": yes_no(pct_change >= 3 and volume_ratio >= 1.2),
            "tail_pullback_holds": yes_no(close >= open_price or close_position >= 92),
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "ma_alignment_up": yes_no(close > ma5 > ma10 > ma20),
            "pullback_to_ma10_or_ma20": "否",
            "close_above_ma5": yes_no(close > ma5),
            "recent_volume_rank_low": "否",
            "close_gt_open": yes_no(close > open_price),
            "kdj_low_turn_up": "否",
            "rsi_low_turn_up": "否",
            "theme_limit_up_count": theme_limit_up_count,
            "theme_rank": theme_rank,
            "theme_tail_reflow": yes_no(pct_change >= 2 and volume_ratio >= 1.1),
            "theme_leader_auction": "",
            "manual_note": manual_note,
            "data_source": data_source,
            "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch latest main-board focus-theme demo data.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-rows", type=int, default=0, help="0 means keep all fetched main-board rows")
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES, help="Rules JSON path for focus theme keywords")
    args = parser.parse_args()

    apply_rules_config(load_rules(args.rules, strict=True))
    existing_snapshot = read_snapshot_csv(args.output)
    if existing_snapshot:
        update_universe_cache(existing_snapshot, "existing_latest_market_data")

    try:
        ths_rows = run_with_timeout("Tonghuashun", THS_TIMEOUT_SECONDS, fetch_ths_all)
        selected = select_demo_rows(ths_rows, args.max_rows)
        trade_dates = sorted({str(row.get("trade_date", "")) for row in selected if row.get("trade_date")})
        trade_date = trade_dates[-1] if trade_dates else datetime.now().strftime("%Y-%m-%d")
        source_name = "Tonghuashun"
    except Exception as ths_exc:
        print(f"Tonghuashun fetch failed, falling back to Eastmoney direct: {ths_exc}")
        try:
            raw_rows = run_with_timeout(
                "Eastmoney",
                EASTMONEY_TIMEOUT_SECONDS,
                fetch_all,
                page_size=args.page_size,
            )
            trade_date = trade_date_from_rows(raw_rows)
            converted = [convert_row(row, trade_date) for row in raw_rows]
            converted_rows = [row for row in converted if row]
            if len(converted_rows) < MIN_FULL_SOURCE_ROWS:
                raise RuntimeError(f"Eastmoney returned only {len(converted_rows)} eligible rows; fallback required")
            update_universe_cache(converted_rows, "eastmoney_push2_snapshot")
            selected = select_demo_rows(converted_rows, args.max_rows)
            source_name = "Eastmoney"
        except Exception as exc:
            print(f"Eastmoney fetch failed, falling back to local universe Sina quotes: {exc}")
            try:
                selected = fetch_sina_universe()
                if args.max_rows > 0:
                    selected = select_demo_rows(selected, args.max_rows)
                trade_dates = sorted({str(row.get("trade_date", "")) for row in selected if row.get("trade_date")})
                trade_date = trade_dates[-1] if trade_dates else datetime.now().strftime("%Y-%m-%d")
                source_name = "SinaUniverse"
            except Exception as exc2:
                print(f"Local universe Sina fetch failed, falling back to Sina focus list: {exc2}")
                try:
                    selected = fetch_sina_focus()
                    update_universe_cache(selected, "sina_hq_focus_snapshot")
                    if args.max_rows > 0:
                        selected = selected[: args.max_rows]
                    trade_dates = sorted({str(row.get("trade_date", "")) for row in selected if row.get("trade_date")})
                    trade_date = trade_dates[-1] if trade_dates else datetime.now().strftime("%Y-%m-%d")
                    source_name = "SinaFocus"
                except Exception as exc3:
                    if not existing_snapshot:
                        raise
                    print(f"Sina focus fetch failed, using existing latest snapshot: {exc3}")
                    selected = select_demo_rows(existing_snapshot, args.max_rows)
                    trade_dates = sorted({str(row.get("trade_date", "")) for row in selected if row.get("trade_date")})
                    trade_date = trade_dates[-1] if trade_dates else datetime.now().strftime("%Y-%m-%d")
                    source_name = "ExistingSnapshot"
    if (
        len(selected) < MIN_FULL_SOURCE_ROWS
        and len(existing_snapshot) >= MIN_FULL_SOURCE_ROWS
        and len(existing_snapshot) > len(selected)
    ):
        print(
            f"New snapshot has only {len(selected)} rows; preserving existing full snapshot with {len(existing_snapshot)} rows"
        )
        selected = select_demo_rows(existing_snapshot, args.max_rows)
        trade_dates = sorted({str(row.get("trade_date", "")) for row in selected if row.get("trade_date")})
        trade_date = trade_dates[-1] if trade_dates else trade_date
        source_name = "ExistingSnapshotPreserved"

    write_csv(args.output, selected)
    print(f"Source: {source_name}")
    print(f"Latest trade date inferred: {trade_date}")
    print(f"Wrote demo CSV: {args.output}")
    print(f"Rows: {len(selected)}")


if __name__ == "__main__":
    main()
