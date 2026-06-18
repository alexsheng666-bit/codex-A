#!/usr/bin/env python3
"""Maintain a paper-trading account from A-pool recommendations."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATES = ROOT / "work" / "normalized_data" / "candidates_latest.csv"
DEFAULT_MARKET = ROOT / "01_原始资料" / "market_data" / "raw_csv" / "latest_market_data.csv"
PAPER_DIR = ROOT / "work" / "paper_trading"
STATE_PATH = PAPER_DIR / "account_state.json"
LEDGER_PATH = PAPER_DIR / "trade_ledger.csv"
SNAPSHOT_PATH = PAPER_DIR / "position_snapshots.csv"
POSITIONS_PATH = PAPER_DIR / "positions_latest.csv"
PERFORMANCE_PATH = PAPER_DIR / "performance_latest.json"
REPORT_PATH = PAPER_DIR / "paper_trading_report.md"
TRADE_GATE_PATH = PAPER_DIR / "trade_gate_latest.json"
QUOTE_ENDPOINTS_PATH = ROOT / "work" / "cloud" / "quote_endpoints.txt"
INITIAL_CAPITAL = 1_000_000.0
BUY_AFTER = time(14, 55)
BUY_BEFORE = time(15, 0)
BUY_TIME_LABEL = "14:55"
TIME_EXIT_AFTER = time(14, 30)
TIME_EXIT_LABEL = "14:30"
LOT_SIZE = 100
DEFAULT_TAKE_PROFIT_PCT = 2.0
DEFAULT_STOP_LOSS_PCT = 2.5
MARKET_TZ = ZoneInfo("Asia/Shanghai")
MAX_EXECUTION_SNAPSHOT_AGE_MINUTES = 10
REALTIME_CONFIRM_LIMIT = 30
REALTIME_TIMEOUT_SECONDS = 8


LEDGER_FIELDS = [
    "trade_date",
    "trade_time",
    "action",
    "stock_code",
    "stock_name",
    "price",
    "shares",
    "amount",
    "pnl_amount",
    "pnl_pct",
    "cash_after",
    "sell_pressure_score",
    "sell_signal",
    "volume_ratio",
    "turnover_rate",
    "note",
]

SNAPSHOT_FIELDS = [
    "trade_date",
    "snapshot_time",
    "stock_code",
    "stock_name",
    "price",
    "open",
    "high",
    "low",
    "volume",
    "turnover_amount",
    "turnover_rate",
    "volume_ratio",
    "vwap_price",
    "close_position_pct",
]


def num(value: object, default: float = 0.0) -> float:
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def market_now() -> datetime:
    return datetime.now(MARKET_TZ).replace(tzinfo=None)


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: List[Dict[str, object]], fields: List[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = fields or []
    if not fieldnames:
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in fieldnames} for row in rows])


def read_ledger() -> List[Dict[str, str]]:
    return read_csv(LEDGER_PATH)


def write_ledger(rows: List[Dict[str, object]]) -> None:
    write_csv(LEDGER_PATH, rows, LEDGER_FIELDS)


def trade_date_from(rows: List[Dict[str, str]]) -> str:
    dates = sorted({row.get("trade_date", "") for row in rows if row.get("trade_date")})
    return dates[-1] if dates else market_now().strftime("%Y-%m-%d")


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def can_buy_tail(trade_date: str, now: datetime) -> bool:
    try:
        parsed = parse_date(trade_date)
    except ValueError:
        return False
    if parsed != now.date():
        return False
    return BUY_AFTER <= now.time() < BUY_BEFORE


def parse_datetime(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.replace("T", " ").replace("Z", "").replace("/", "-")
    if "." in raw:
        raw = raw.split(".", 1)[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def latest_snapshot_time(rows: List[Dict[str, str]], trade_date: str) -> datetime | None:
    times = []
    for row in rows:
        if row.get("trade_date") and row.get("trade_date") != trade_date:
            continue
        captured = parse_datetime(row.get("captured_at") or row.get("time"))
        if captured:
            times.append(captured)
    return max(times) if times else None


def snapshot_freshness(rows: List[Dict[str, str]], trade_date: str, now: datetime) -> Dict[str, object]:
    latest = latest_snapshot_time(rows, trade_date)
    if not latest:
        return {
            "ok": False,
            "latest_at": "",
            "age_minutes": None,
            "message": "未识别到行情快照时间，禁止自动交易",
        }
    age = max(0.0, (now - latest).total_seconds() / 60)
    ok = latest.date() == now.date() and age <= MAX_EXECUTION_SNAPSHOT_AGE_MINUTES
    if ok:
        message = f"行情快照 {latest.strftime('%H:%M')}，距当前约 {age:.1f} 分钟，允许进入执行校验"
    else:
        message = (
            f"行情快照过旧：最新 {latest.strftime('%Y-%m-%d %H:%M:%S')}，"
            f"距当前约 {age:.1f} 分钟，禁止自动交易"
        )
    return {
        "ok": ok,
        "latest_at": latest.strftime("%Y-%m-%d %H:%M:%S"),
        "age_minutes": round(age, 1),
        "message": message,
    }


def load_state(initial_capital: float) -> Dict[str, object]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {
        "initial_capital": round(initial_capital, 2),
        "cash": round(initial_capital, 2),
        "equity": round(initial_capital, 2),
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "cumulative_pnl": 0.0,
        "cumulative_return_pct": 0.0,
        "positions": [],
        "last_trade_date": "",
        "last_updated": "",
    }


def save_state(state: Dict[str, object]) -> None:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def market_by_code(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {row.get("stock_code", ""): row for row in rows if row.get("stock_code")}


def quote_price(row: Dict[str, str] | None, fallback: float) -> float:
    if not row:
        return fallback
    return num(row.get("close"), fallback) or fallback


def quote_snapshot_time(row: Dict[str, str] | None) -> str:
    if not row:
        return ""
    captured = str(row.get("captured_at") or row.get("time") or "").strip()
    match = captured[-8:-3] if len(captured) >= 16 else ""
    return match if ":" in match else ""


def eastmoney_secid(code: str) -> str:
    clean = "".join(ch for ch in str(code or "") if ch.isdigit()).zfill(6)[-6:]
    if not clean:
        return ""
    return f"1.{clean}" if clean.startswith("6") else f"0.{clean}"


def normalize_code(code: object) -> str:
    return "".join(ch for ch in str(code or "") if ch.isdigit()).zfill(6)[-6:]


def read_quote_endpoints() -> List[str]:
    endpoints: List[str] = []
    if QUOTE_ENDPOINTS_PATH.exists():
        for line in QUOTE_ENDPOINTS_PATH.read_text(encoding="utf-8").splitlines():
            item = line.strip()
            if not item or item.startswith("#"):
                continue
            endpoints.append(item.rstrip("/"))
    return endpoints


def fetch_json(url: str, headers: Dict[str, str] | None = None, timeout: int = REALTIME_TIMEOUT_SECONDS) -> Dict[str, object]:
    request = Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_eastmoney_realtime(codes: List[str]) -> Tuple[Dict[str, Dict[str, object]], str]:
    secids = [eastmoney_secid(code) for code in codes]
    secids = [item for item in secids if item]
    if not secids:
        return {}, "eastmoney"
    fields = "f12,f14,f2,f3,f5,f6,f8,f10,f15,f16,f17,f18"
    query = urlencode({"fltt": "2", "fields": fields, "secids": ",".join(secids)})
    url = f"https://push2.eastmoney.com/api/qt/ulist.np/get?{query}"
    payload = fetch_json(url, headers={"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"})
    rows = ((payload.get("data") or {}).get("diff") or []) if isinstance(payload, dict) else []
    now_text = market_now().strftime("%Y-%m-%d %H:%M:%S")
    quotes: Dict[str, Dict[str, object]] = {}
    for row in rows:
        code = normalize_code(row.get("f12"))
        price = num(row.get("f2"))
        pre_close = num(row.get("f18"))
        if not code or price <= 0:
            continue
        quotes[code] = {
            "code": code,
            "name": row.get("f14") or "",
            "price": price,
            "open": num(row.get("f17")),
            "pre_close": pre_close,
            "high": num(row.get("f15")),
            "low": num(row.get("f16")),
            "volume": num(row.get("f5")),
            "amount": num(row.get("f6")),
            "turnover_rate": num(row.get("f8")),
            "volume_ratio": num(row.get("f10")),
            "pct_change": num(row.get("f3")),
            "time": now_text,
            "source": "eastmoney_realtime",
        }
    return quotes, "eastmoney"


def fetch_worker_realtime(codes: List[str]) -> Tuple[Dict[str, Dict[str, object]], str]:
    for endpoint in read_quote_endpoints():
        url = f"{endpoint}/quotes?{urlencode({'codes': ','.join(codes)})}"
        try:
            payload = fetch_json(url)
        except Exception:
            continue
        if not payload.get("ok"):
            continue
        raw_quotes = payload.get("quotes") or {}
        quotes: Dict[str, Dict[str, object]] = {}
        for code, quote in raw_quotes.items():
            clean = normalize_code(code)
            if not clean or not isinstance(quote, dict):
                continue
            quotes[clean] = {
                "code": clean,
                "name": quote.get("name") or "",
                "price": num(quote.get("price")),
                "open": num(quote.get("open")),
                "pre_close": num(quote.get("pre_close")),
                "high": num(quote.get("high")),
                "low": num(quote.get("low")),
                "volume": num(quote.get("volume")),
                "amount": num(quote.get("amount")),
                "turnover_rate": num(quote.get("turnover_rate")),
                "volume_ratio": num(quote.get("volume_ratio")),
                "pct_change": num(quote.get("pct_change")),
                "time": quote.get("time") or payload.get("updated_at") or market_now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": payload.get("source") or "worker_quote",
            }
        if quotes:
            return quotes, f"worker:{endpoint}"
    return {}, "worker"


def fetch_realtime_quotes(codes: List[str]) -> Tuple[Dict[str, Dict[str, object]], str, List[str]]:
    errors: List[str] = []
    clean_codes = [normalize_code(code) for code in codes]
    clean_codes = [code for code in clean_codes if code]
    quotes: Dict[str, Dict[str, object]] = {}
    sources: List[str] = []
    try:
        eastmoney_quotes, source = fetch_eastmoney_realtime(clean_codes)
        if eastmoney_quotes:
            quotes.update(eastmoney_quotes)
            sources.append(source)
    except Exception as exc:
        errors.append(f"Eastmoney小批量实时确认失败：{exc}")
    missing_codes = [code for code in clean_codes if code not in quotes]
    try:
        if missing_codes or not quotes:
            worker_quotes, source = fetch_worker_realtime(missing_codes or clean_codes)
            if worker_quotes:
                quotes.update(worker_quotes)
                sources.append(source)
    except Exception as exc:
        errors.append(f"Worker实时确认失败：{exc}")
    return quotes, "+".join(sources) if sources else "none", errors


def quote_time_ok(quote: Dict[str, object], trade_date: str, now: datetime) -> bool:
    quote_time = parse_datetime(quote.get("time"))
    if not quote_time:
        return False
    if quote_time.date().strftime("%Y-%m-%d") != trade_date:
        return False
    age = abs((now - quote_time).total_seconds()) / 60
    return age <= MAX_EXECUTION_SNAPSHOT_AGE_MINUTES


def realtime_required_fields_ok(quote: Dict[str, object]) -> bool:
    return (
        num(quote.get("price")) > 0
        and num(quote.get("volume")) > 0
        and num(quote.get("amount")) > 0
        and num(quote.get("turnover_rate")) > 0
        and num(quote.get("volume_ratio")) > 0
    )


def apply_realtime_quote(row: Dict[str, str], quote: Dict[str, object]) -> None:
    price = num(quote.get("price"))
    if price <= 0:
        return
    row["buy_point"] = f"{price:.2f}"
    row["close"] = f"{price:.2f}"
    row["open"] = f"{num(quote.get('open')):.2f}" if num(quote.get("open")) else row.get("open", "")
    row["high"] = f"{num(quote.get('high')):.2f}" if num(quote.get("high")) else row.get("high", "")
    row["low"] = f"{num(quote.get('low')):.2f}" if num(quote.get("low")) else row.get("low", "")
    row["pre_close"] = f"{num(quote.get('pre_close')):.2f}" if num(quote.get("pre_close")) else row.get("pre_close", "")
    row["pct_change"] = f"{num(quote.get('pct_change')):.2f}"
    row["volume"] = str(int(num(quote.get("volume"))))
    row["turnover_amount"] = str(int(num(quote.get("amount"))))
    row["turnover_rate"] = f"{num(quote.get('turnover_rate')):.2f}"
    row["volume_ratio"] = f"{num(quote.get('volume_ratio')):.2f}"
    row["captured_at"] = str(quote.get("time") or market_now().strftime("%Y-%m-%d %H:%M:%S"))
    row["data_source"] = str(quote.get("source") or "realtime_confirm")


def trade_gate_base(trade_date: str, now: datetime, snapshot_status: Dict[str, object]) -> Dict[str, object]:
    return {
        "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": trade_date,
        "buy_window": f"{BUY_TIME_LABEL}-15:00",
        "snapshot_ok": bool(snapshot_status.get("ok")),
        "snapshot_latest_at": snapshot_status.get("latest_at", ""),
        "snapshot_age_minutes": snapshot_status.get("age_minutes"),
        "status": "快照可用" if snapshot_status.get("ok") else "快照过旧",
        "message": snapshot_status.get("message", ""),
        "execution_allowed": bool(snapshot_status.get("ok")),
        "realtime_confirmed": False,
        "realtime_source": "",
        "a_pool_count": 0,
        "confirmed_codes": [],
        "missing_codes": [],
        "stale_codes": [],
        "field_missing_codes": [],
        "errors": [],
    }


def write_trade_gate(gate: Dict[str, object]) -> None:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    TRADE_GATE_PATH.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def confirm_a_pool_realtime(
    a_rows: List[Dict[str, str]],
    trade_date: str,
    now: datetime,
) -> Dict[str, object]:
    checked_rows = a_rows[:REALTIME_CONFIRM_LIMIT]
    codes = [normalize_code(row.get("stock_code")) for row in checked_rows]
    codes = [code for code in codes if code]
    if not codes:
        return {
            "ok": False,
            "source": "",
            "confirmed_codes": [],
            "missing_codes": [],
            "stale_codes": [],
            "field_missing_codes": [],
            "errors": [],
            "message": "A池为空，未进入尾盘买入",
        }
    quotes, source, errors = fetch_realtime_quotes(codes)
    missing = [code for code in codes if code not in quotes]
    stale = [code for code in codes if code in quotes and not quote_time_ok(quotes[code], trade_date, now)]
    field_missing = [
        code
        for code in codes
        if code in quotes and code not in stale and not realtime_required_fields_ok(quotes[code])
    ]
    confirmed = [
        code
        for code in codes
        if code in quotes and code not in stale and code not in field_missing
    ]
    ok = bool(codes) and not missing and not stale and not field_missing
    if ok:
        for row in checked_rows:
            code = normalize_code(row.get("stock_code"))
            if code in quotes:
                apply_realtime_quote(row, quotes[code])
        message = f"A池 {len(confirmed)} 只已完成实时二次确认，允许尾盘模拟买入"
    else:
        reasons = []
        if missing:
            reasons.append(f"缺少实时行情 {len(missing)} 只")
        if stale:
            reasons.append(f"行情时间异常 {len(stale)} 只")
        if field_missing:
            reasons.append(f"量能/换手字段不足 {len(field_missing)} 只")
        if errors:
            reasons.append("；".join(errors))
        message = "A池实时二次确认未通过，禁止尾盘模拟买入：" + "；".join(reasons or ["实时行情不可用"])
    return {
        "ok": ok,
        "source": source,
        "confirmed_codes": confirmed,
        "missing_codes": missing,
        "stale_codes": stale,
        "field_missing_codes": field_missing,
        "errors": errors,
        "message": message,
    }


def metric_summary(quote: Dict[str, str] | None) -> str:
    if not quote:
        return "量能数据缺失"
    parts = []
    volume_ratio = num(quote.get("volume_ratio"))
    turnover_rate = num(quote.get("turnover_rate"))
    amount = num(quote.get("turnover_amount") or quote.get("amount"))
    if volume_ratio:
        parts.append(f"量比{volume_ratio:.2f}")
    if turnover_rate:
        parts.append(f"换手{turnover_rate:.2f}%")
    if amount:
        parts.append(f"成交额{amount / 100_000_000:.1f}亿")
    return "，".join(parts) if parts else "量能数据缺失"


def snapshot_row(position: Dict[str, object], quote: Dict[str, str], trade_date: str) -> Dict[str, object]:
    price = quote_price(quote, float(position.get("entry_price", 0.0)))
    return {
        "trade_date": trade_date,
        "snapshot_time": quote_snapshot_time(quote) or market_now().strftime("%H:%M"),
        "stock_code": position.get("stock_code", ""),
        "stock_name": position.get("stock_name", ""),
        "price": f"{price:.2f}",
        "open": quote.get("open", ""),
        "high": quote.get("high", ""),
        "low": quote.get("low", ""),
        "volume": quote.get("volume", ""),
        "turnover_amount": quote.get("turnover_amount") or quote.get("amount", ""),
        "turnover_rate": quote.get("turnover_rate", ""),
        "volume_ratio": quote.get("volume_ratio", ""),
        "vwap_price": quote.get("vwap_price", ""),
        "close_position_pct": quote.get("close_position_pct", ""),
    }


def previous_snapshot(
    snapshots: List[Dict[str, str]],
    code: str,
    trade_date: str,
    snapshot_time: str,
) -> Dict[str, str] | None:
    matches = [
        row
        for row in snapshots
        if row.get("stock_code") == code
        and row.get("trade_date") == trade_date
        and row.get("snapshot_time", "") < snapshot_time
    ]
    return sorted(matches, key=lambda row: row.get("snapshot_time", ""))[-1] if matches else None


def append_position_snapshots(
    snapshots: List[Dict[str, str]],
    positions: List[Dict[str, object]],
    quotes: Dict[str, Dict[str, str]],
    trade_date: str,
) -> None:
    existing_keys = {
        (row.get("trade_date", ""), row.get("snapshot_time", ""), row.get("stock_code", ""))
        for row in snapshots
    }
    for position in positions:
        code = str(position.get("stock_code", ""))
        quote = quotes.get(code)
        if not quote:
            continue
        row = snapshot_row(position, quote, trade_date)
        key = (str(row.get("trade_date", "")), str(row.get("snapshot_time", "")), str(row.get("stock_code", "")))
        if key in existing_keys:
            continue
        snapshots.append(row)
        existing_keys.add(key)


def write_snapshots(rows: List[Dict[str, object]]) -> None:
    write_csv(SNAPSHOT_PATH, rows, SNAPSHOT_FIELDS)


def paper_sell_rule() -> str:
    return f"严格遵守 T+1：当日尾盘买入，最早次日按止盈/止损纪律退出；未触发则 {TIME_EXIT_LABEL} 时间止损全部卖出"


def can_time_exit(current_trade_date: str, now: datetime) -> bool:
    try:
        parsed = parse_date(current_trade_date)
    except ValueError:
        return False
    if parsed < now.date():
        return True
    if parsed > now.date():
        return False
    return now.time() >= TIME_EXIT_AFTER


def sell_pressure(position: Dict[str, object], quote: Dict[str, str], prev: Dict[str, str] | None) -> Dict[str, object]:
    entry_price = float(position.get("entry_price", 0.0))
    open_price = num(quote.get("open"), entry_price) or entry_price
    high = num(quote.get("high"), open_price) or open_price
    low = num(quote.get("low"), open_price) or open_price
    close = num(quote.get("close"), open_price) or open_price
    first_take = num(position.get("first_take_profit_point")) or round(entry_price * (1 + DEFAULT_TAKE_PROFIT_PCT / 100), 2)
    volume_ratio = num(quote.get("volume_ratio"))
    turnover_rate = num(quote.get("turnover_rate"))
    close_position = num(quote.get("close_position_pct"))
    vwap = num(quote.get("vwap_price"))
    amount = num(quote.get("turnover_amount") or quote.get("amount"))
    prev_price = num(prev.get("price")) if prev else 0.0
    prev_amount = num(prev.get("turnover_amount")) if prev else 0.0
    amount_delta = max(0.0, amount - prev_amount) if prev_amount else 0.0
    price_delta_pct = round((close - prev_price) / prev_price * 100, 2) if prev_price else 0.0
    above_vwap = bool(vwap and close >= vwap)

    score = 35 if high >= first_take else 0
    if vwap and close < vwap:
        score += 25
    if close_position and close_position < 70:
        score += 20
    if volume_ratio >= 3.2:
        score += 15
    if turnover_rate >= 12:
        score += 15
    if amount_delta >= 50_000_000 and price_delta_pct <= -0.3:
        score += 20
    if close >= entry_price * 1.04 and close_position and close_position < 82:
        score += 10
    if above_vwap and close_position >= 85:
        score -= 20
    if 1.2 <= volume_ratio <= 2.8 and price_delta_pct >= 0:
        score -= 10
    score = max(0, min(100, int(round(score))))

    if score >= 75:
        signal = "卖出压力高"
    elif score >= 55:
        signal = "卖出压力中"
    else:
        signal = "承接较强"
    detail = f"{signal}{score}/100；{metric_summary(quote)}"
    if prev_price:
        detail += f"，较上次{price_delta_pct:+.2f}%"
    return {
        "score": score,
        "signal": signal,
        "detail": detail,
        "volume_ratio": volume_ratio,
        "turnover_rate": turnover_rate,
    }


def sell_decision(
    position: Dict[str, object],
    quote: Dict[str, str],
    current_trade_date: str,
    now: datetime,
    prev_snapshot: Dict[str, str] | None,
) -> tuple[float, str, str, Dict[str, object], bool]:
    entry_price = float(position.get("entry_price", 0.0))
    open_price = num(quote.get("open"), entry_price) or entry_price
    high = num(quote.get("high"), open_price) or open_price
    low = num(quote.get("low"), open_price) or open_price
    close = num(quote.get("close"), open_price) or open_price
    first_take = num(position.get("first_take_profit_point")) or round(entry_price * (1 + DEFAULT_TAKE_PROFIT_PCT / 100), 2)
    defensive_stop = num(position.get("defensive_stop_point")) or round(entry_price * (1 - DEFAULT_STOP_LOSS_PCT / 100), 2)
    snapshot_time = quote_snapshot_time(quote)
    pressure = sell_pressure(position, quote, prev_snapshot)
    sell_all_on_take = int(pressure["score"]) >= 75

    if open_price <= entry_price * 0.985:
        return open_price, f"T+1 次日 9:35 低开超过 -1.5%，按开盘价近似卖出；{pressure['detail']}", "09:35", pressure, True
    if open_price >= first_take and not position.get("first_take_done"):
        action = "量能压力偏高，卖出全部" if sell_all_on_take else "承接尚可，先卖半仓"
        return first_take, f"T+1 次日开盘已越过第一止盈，按第一止盈点保守卖出；{pressure['detail']}，{action}", "09:30", pressure, sell_all_on_take
    if low <= defensive_stop:
        label = f"截至{snapshot_time}快照已触发" if snapshot_time else "已触发"
        return defensive_stop, f"T+1 次日{label}防守止损，按止损点近似卖出；{pressure['detail']}", snapshot_time, pressure, True
    if high >= first_take and not position.get("first_take_done"):
        label = f"截至{snapshot_time}快照已触发" if snapshot_time else "已触发"
        action = "量能压力偏高，卖出全部" if sell_all_on_take else "承接尚可，先卖半仓"
        return first_take, f"T+1 次日{label}第一止盈，按第一止盈点卖出；{pressure['detail']}，{action}", snapshot_time, pressure, sell_all_on_take
    if can_time_exit(current_trade_date, now):
        return close, f"T+1 次日未触发止盈止损，{TIME_EXIT_LABEL} 时间止损全部卖出；{pressure['detail']}", TIME_EXIT_LABEL, pressure, True
    return 0.0, f"T+1 次日未触发止盈止损，等待 {TIME_EXIT_LABEL} 时间止损；{pressure['detail']}", "", pressure, False


def append_ledger(
    ledger: List[Dict[str, object]],
    trade_date: str,
    trade_time: str,
    action: str,
    code: str,
    name: str,
    price: float,
    shares: int,
    amount: float,
    pnl_amount: float,
    pnl_pct: float,
    cash_after: float,
    note: str,
    sell_pressure_score: object = "",
    sell_signal: str = "",
    volume_ratio: object = "",
    turnover_rate: object = "",
) -> None:
    ledger.append(
        {
            "trade_date": trade_date,
            "trade_time": trade_time,
            "action": action,
            "stock_code": code,
            "stock_name": name,
            "price": f"{price:.2f}",
            "shares": shares,
            "amount": f"{amount:.2f}",
            "pnl_amount": f"{pnl_amount:.2f}",
            "pnl_pct": f"{pnl_pct:.2f}",
            "cash_after": f"{cash_after:.2f}",
            "sell_pressure_score": sell_pressure_score,
            "sell_signal": sell_signal,
            "volume_ratio": volume_ratio,
            "turnover_rate": turnover_rate,
            "note": note,
        }
    )


def infer_ledger_time(row: Dict[str, object], quotes: Dict[str, Dict[str, str]], current_trade_date: str) -> str:
    direct = str(row.get("trade_time") or row.get("time") or "").strip()
    note = str(row.get("note") or "")
    import re

    found = re.search(r"(\d{1,2}:\d{2})", note)
    if found:
        return found.group(1).zfill(5)
    if row.get("action") == "BUY":
        return direct or BUY_TIME_LABEL
    if row.get("trade_date") != current_trade_date:
        if direct and ("截至" in note or "开盘已越过" in note or "时间止损" in note):
            return direct
            return direct or "未记录"
    if direct:
        return direct
    quote = quotes.get(str(row.get("stock_code") or "")) if row.get("trade_date") == current_trade_date else None
    if row.get("action") == "SELL" and "第一止盈" in note:
        sell_price = num(row.get("price"))
        if quote and num(quote.get("open")) >= sell_price > 0:
            return "09:30"
        return quote_snapshot_time(quote)
    if row.get("action") == "SELL" and "防守止损" in note:
        sell_price = num(row.get("price"))
        if quote and num(quote.get("open")) <= sell_price:
            return "09:30"
        return quote_snapshot_time(quote)
    return ""


def backfill_ledger_fields(ledger: List[Dict[str, object]], quotes: Dict[str, Dict[str, str]], current_trade_date: str) -> None:
    for row in ledger:
        row["trade_time"] = infer_ledger_time(row, quotes, current_trade_date)
        if row.get("trade_date") != current_trade_date or row.get("action") != "SELL":
            continue
        quote = quotes.get(str(row.get("stock_code") or ""))
        if quote:
            if not row.get("volume_ratio"):
                value = num(quote.get("volume_ratio"))
                row["volume_ratio"] = f"{value:.2f}" if value else ""
            if not row.get("turnover_rate"):
                value = num(quote.get("turnover_rate"))
                row["turnover_rate"] = f"{value:.2f}" if value else ""
            if not row.get("sell_signal") or not row.get("sell_pressure_score"):
                shares = num(row.get("shares"))
                amount = num(row.get("amount"))
                pnl = num(row.get("pnl_amount"))
                cost = max(0.0, amount - pnl)
                entry_price = cost / shares if shares else num(row.get("price"))
                pseudo_position = {
                    "entry_price": entry_price,
                    "first_take_profit_point": row.get("price"),
                }
                pressure = sell_pressure(pseudo_position, quote, None)
                row["sell_pressure_score"] = pressure.get("score", "")
                row["sell_signal"] = pressure.get("signal", "")
        note = str(row.get("note") or "")
        if "第一止盈" not in note or "截至" in note or "开盘已越过" in note:
            continue
        sell_price = num(row.get("price"))
        if quote and num(quote.get("open")) >= sell_price > 0:
            row["note"] = note.replace("T+1 次日触发第一止盈", "T+1 次日开盘已越过第一止盈")
            continue
        snapshot_time = quote_snapshot_time(quote)
        if snapshot_time:
            row["note"] = note.replace("T+1 次日触发第一止盈", f"T+1 次日截至{snapshot_time}快照已触发第一止盈")


def close_old_positions(
    state: Dict[str, object],
    ledger: List[Dict[str, object]],
    current_trade_date: str,
    quotes: Dict[str, Dict[str, str]],
    snapshots: List[Dict[str, str]],
    now: datetime,
) -> None:
    cash = float(state.get("cash", 0.0))
    realized_total = float(state.get("realized_pnl", 0.0))
    positions = []
    for position in list(state.get("positions", [])):
        entry_date = str(position.get("entry_date", ""))
        if entry_date >= current_trade_date:
            positions.append(position)
            continue
        code = str(position.get("stock_code", ""))
        shares = int(position.get("shares", 0))
        entry_price = float(position.get("entry_price", 0.0))
        quote = quotes.get(code)
        if not quote:
            positions.append(position)
            continue
        snapshot_time = quote_snapshot_time(quote)
        prev = previous_snapshot(snapshots, code, current_trade_date, snapshot_time)
        sell_price, sell_note, sell_time, pressure, sell_all = sell_decision(position, quote, current_trade_date, now, prev)
        if sell_price <= 0:
            positions.append(position)
            continue
        if "第一止盈" in sell_note and not sell_all:
            sell_shares = max(LOT_SIZE, int((shares * 0.5) // LOT_SIZE) * LOT_SIZE)
            sell_shares = min(sell_shares, shares)
        else:
            sell_shares = shares
        sell_amount = round(sell_price * shares, 2)
        cost = round(entry_price * sell_shares, 2)
        sell_amount = round(sell_price * sell_shares, 2)
        pnl = round(sell_amount - cost, 2)
        pnl_pct = round(pnl / cost * 100, 2) if cost else 0.0
        cash = round(cash + sell_amount, 2)
        realized_total = round(realized_total + pnl, 2)
        append_ledger(
            ledger,
            current_trade_date,
            sell_time,
            "SELL",
            code,
            str(position.get("stock_name", "")),
            sell_price,
            sell_shares,
            sell_amount,
            pnl,
            pnl_pct,
            cash,
            f"{sell_note}{'，剩余仓位继续强势跟踪' if sell_shares < shares else ''}；盈亏滚入下一轮本金",
            pressure.get("score", ""),
            str(pressure.get("signal", "")),
            f"{float(pressure.get('volume_ratio') or 0):.2f}" if pressure.get("volume_ratio") else "",
            f"{float(pressure.get('turnover_rate') or 0):.2f}" if pressure.get("turnover_rate") else "",
        )
        remaining_shares = shares - sell_shares
        if remaining_shares > 0:
            position["shares"] = remaining_shares
            position["cost"] = round(entry_price * remaining_shares, 2)
            if "第一止盈" in sell_note:
                position["first_take_done"] = True
            positions.append(position)
    state["cash"] = cash
    state["realized_pnl"] = realized_total
    state["positions"] = positions


def bought_today(ledger: List[Dict[str, object]], trade_date: str) -> bool:
    return any(row.get("trade_date") == trade_date and row.get("action") == "BUY" for row in ledger)


def buy_today_a_pool(
    state: Dict[str, object],
    ledger: List[Dict[str, object]],
    candidates: List[Dict[str, str]],
    trade_date: str,
) -> None:
    if bought_today(ledger, trade_date):
        return
    if state.get("positions"):
        return
    a_rows = [row for row in candidates if row.get("pool_level") == "A"]
    if not a_rows:
        return

    cash = float(state.get("cash", 0.0))
    per_stock_cash = cash / len(a_rows)
    positions = []
    for row in a_rows:
        price = num(row.get("buy_point")) or num(row.get("close"))
        if price <= 0:
            continue
        shares = int(per_stock_cash // (price * LOT_SIZE)) * LOT_SIZE
        if shares <= 0:
            continue
        amount = round(price * shares, 2)
        if amount > cash:
            shares = int(cash // (price * LOT_SIZE)) * LOT_SIZE
            amount = round(price * shares, 2)
        if shares <= 0:
            continue
        cash = round(cash - amount, 2)
        position = {
            "entry_date": trade_date,
            "entry_time": BUY_TIME_LABEL,
            "stock_code": row.get("stock_code", ""),
            "stock_name": row.get("stock_name", ""),
            "shares": shares,
            "entry_price": round(price, 2),
            "cost": amount,
            "current_price": round(price, 2),
            "market_value": amount,
            "unrealized_pnl": 0.0,
            "unrealized_return_pct": 0.0,
            "pool_rank": row.get("pool_rank", ""),
            "candidate_score": row.get("candidate_score", ""),
            "first_take_profit_point": row.get("first_take_profit_point", ""),
            "defensive_stop_point": row.get("defensive_stop_point", ""),
            "first_take_done": False,
            "sell_rule": paper_sell_rule(),
        }
        positions.append(position)
        append_ledger(
            ledger,
            trade_date,
            BUY_TIME_LABEL,
            "BUY",
            row.get("stock_code", ""),
            row.get("stock_name", ""),
            price,
            shares,
            amount,
            0.0,
            0.0,
            cash,
            f"尾盘{BUY_TIME_LABEL}模拟买入，按重点关注平均分配账户余额；严格遵守 T+1，当日不卖",
        )
    state["cash"] = cash
    state["positions"] = positions
    state["last_trade_date"] = trade_date


def mark_to_market(state: Dict[str, object], quotes: Dict[str, Dict[str, str]]) -> None:
    cash = float(state.get("cash", 0.0))
    market_value = 0.0
    unrealized = 0.0
    positions = []
    for position in list(state.get("positions", [])):
        entry_price = float(position.get("entry_price", 0.0))
        shares = int(position.get("shares", 0))
        current = quote_price(quotes.get(str(position.get("stock_code", ""))), entry_price)
        value = round(current * shares, 2)
        cost = float(position.get("cost", entry_price * shares))
        pnl = round(value - cost, 2)
        pnl_pct = round(pnl / cost * 100, 2) if cost else 0.0
        position["current_price"] = round(current, 2)
        position["market_value"] = value
        position["unrealized_pnl"] = pnl
        position["unrealized_return_pct"] = pnl_pct
        position["sell_rule"] = paper_sell_rule()
        market_value += value
        unrealized += pnl
        positions.append(position)
    equity = round(cash + market_value, 2)
    initial = float(state.get("initial_capital", INITIAL_CAPITAL))
    realized = float(state.get("realized_pnl", 0.0))
    state["positions"] = positions
    state["cash"] = round(cash, 2)
    state["market_value"] = round(market_value, 2)
    state["unrealized_pnl"] = round(unrealized, 2)
    state["equity"] = equity
    state["cumulative_pnl"] = round(equity - initial, 2)
    state["cumulative_return_pct"] = round((equity - initial) / initial * 100, 2) if initial else 0.0
    state["realized_return_pct"] = round(realized / initial * 100, 2) if initial else 0.0
    state["last_updated"] = market_now().strftime("%Y-%m-%d %H:%M:%S")


def write_outputs(
    state: Dict[str, object],
    ledger: List[Dict[str, object]],
    trade_date: str,
    note: str,
    trade_gate: Dict[str, object],
) -> None:
    positions = list(state.get("positions", []))
    write_ledger(ledger)
    write_csv(
        POSITIONS_PATH,
        positions,
        [
            "entry_date",
            "entry_time",
            "stock_code",
            "stock_name",
            "shares",
            "entry_price",
            "cost",
            "current_price",
            "market_value",
            "unrealized_pnl",
            "unrealized_return_pct",
            "pool_rank",
            "candidate_score",
            "first_take_profit_point",
            "defensive_stop_point",
            "first_take_done",
            "sell_rule",
        ],
    )
    performance = {
        "trade_date": trade_date,
        "initial_capital": state.get("initial_capital", INITIAL_CAPITAL),
        "cash": state.get("cash", 0.0),
        "market_value": state.get("market_value", 0.0),
        "equity": state.get("equity", 0.0),
        "realized_pnl": state.get("realized_pnl", 0.0),
        "unrealized_pnl": state.get("unrealized_pnl", 0.0),
        "cumulative_pnl": state.get("cumulative_pnl", 0.0),
        "cumulative_return_pct": state.get("cumulative_return_pct", 0.0),
        "position_count": len(positions),
        "last_updated": state.get("last_updated", ""),
        "note": note,
        "trade_gate": trade_gate,
    }
    PERFORMANCE_PATH.write_text(json.dumps(performance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_trade_gate(trade_gate)

    lines = [
        "# 模拟交易账户",
        "",
        "本账户仅用于策略复盘和纸面交易记录，不构成真实交易指令。",
        "",
        f"- 交易日：{trade_date}",
        f"- 初始本金：{float(state.get('initial_capital', INITIAL_CAPITAL)):,.2f}",
        f"- 当前权益：{float(state.get('equity', 0.0)):,.2f}",
        f"- 累计盈亏：{float(state.get('cumulative_pnl', 0.0)):,.2f}",
        f"- 累计收益率：{float(state.get('cumulative_return_pct', 0.0)):.2f}%",
        f"- 当前持仓：{len(positions)} 只",
        f"- 说明：{note}",
        "- T+1规则：当日尾盘买入，最早下一交易日卖出；当前日内不会卖出。",
        "",
    ]
    if positions:
        lines.extend(["| 股票 | 持仓 | 买入价 | 最新价 | 市值 | 浮盈亏 | 浮盈亏率 |", "|---|---:|---:|---:|---:|---:|---:|"])
        for row in positions:
            lines.append(
                f"| {row.get('stock_code')} {row.get('stock_name')} | {row.get('shares')} | "
                f"{float(row.get('entry_price', 0.0)):.2f} | {float(row.get('current_price', 0.0)):.2f} | "
                f"{float(row.get('market_value', 0.0)):,.2f} | {float(row.get('unrealized_pnl', 0.0)):,.2f} | "
                f"{float(row.get('unrealized_return_pct', 0.0)):.2f}% |"
            )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update paper-trading account from A-pool candidates.")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--market", type=Path, default=DEFAULT_MARKET)
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    args = parser.parse_args()

    candidates = read_csv(args.candidates)
    market_rows = read_csv(args.market)
    trade_date = trade_date_from(candidates or market_rows)
    quotes = market_by_code(market_rows)
    state = load_state(args.initial_capital)
    ledger: List[Dict[str, object]] = list(read_ledger())
    snapshots: List[Dict[str, str]] = read_csv(SNAPSHOT_PATH)
    backfill_ledger_fields(ledger, quotes, trade_date)

    now = market_now()
    snapshot_status = snapshot_freshness(market_rows, trade_date, now)
    trade_gate = trade_gate_base(trade_date, now, snapshot_status)
    pre_close_positions = list(state.get("positions", []))
    has_sell_candidates = any(str(position.get("entry_date", "")) < trade_date for position in pre_close_positions)
    buy_window_open = can_buy_tail(trade_date, now)
    execution_needs_fresh = has_sell_candidates or buy_window_open
    note = "未到14:55，等待尾盘模拟买入"
    if execution_needs_fresh and not snapshot_status.get("ok"):
        trade_gate["execution_allowed"] = False
        trade_gate["status"] = "闸门关闭"
        note = str(snapshot_status.get("message") or "行情快照过旧，禁止自动交易")
    else:
        close_old_positions(state, ledger, trade_date, quotes, snapshots, now)
        append_position_snapshots(snapshots, pre_close_positions, quotes, trade_date)
    if can_buy_tail(trade_date, now):
        a_rows = [row for row in candidates if row.get("pool_level") == "A"]
        trade_gate["a_pool_count"] = len(a_rows)
        if not snapshot_status.get("ok"):
            trade_gate["execution_allowed"] = False
            trade_gate["status"] = "闸门关闭"
            note = str(snapshot_status.get("message") or "行情快照过旧，禁止尾盘模拟买入")
        elif bought_today(ledger, trade_date):
            note = "当日已建仓，不重复买入"
            trade_gate["message"] = note
            trade_gate["status"] = "已建仓"
        elif state.get("positions"):
            note = "账户仍有持仓，不重复买入"
            trade_gate["message"] = note
            trade_gate["status"] = "已有持仓"
        elif not a_rows:
            note = "暂无A池候选，不进行尾盘买入"
            trade_gate["message"] = note
            trade_gate["status"] = "无A池"
        else:
            confirm = confirm_a_pool_realtime(a_rows, trade_date, now)
            trade_gate.update(
                {
                    "realtime_confirmed": bool(confirm.get("ok")),
                    "realtime_source": confirm.get("source", ""),
                    "confirmed_codes": confirm.get("confirmed_codes", []),
                    "missing_codes": confirm.get("missing_codes", []),
                    "stale_codes": confirm.get("stale_codes", []),
                    "field_missing_codes": confirm.get("field_missing_codes", []),
                    "errors": confirm.get("errors", []),
                    "message": confirm.get("message", ""),
                    "execution_allowed": bool(confirm.get("ok")),
                    "status": "实时确认通过" if confirm.get("ok") else "闸门关闭",
                }
            )
            if confirm.get("ok"):
                before_buys = len([row for row in ledger if row.get("action") == "BUY"])
                buy_today_a_pool(state, ledger, candidates, trade_date)
                after_buys = len([row for row in ledger if row.get("action") == "BUY"])
                note = "已按A池实时二次确认结果平均模拟建仓" if after_buys > before_buys else "二次确认通过，但账户状态不满足重复买入"
                trade_gate["message"] = note
            else:
                note = str(confirm.get("message") or "A池实时二次确认未通过，禁止尾盘模拟买入")
    else:
        try:
            is_current_trade_day = parse_date(trade_date) == now.date()
        except ValueError:
            is_current_trade_day = False
        if is_current_trade_day and now.time() >= BUY_BEFORE:
            note = "已过14:55-15:00买入窗口，盘后不再新增模拟买入"
            if not snapshot_status.get("ok"):
                note = f"{note}；{snapshot_status.get('message')}"
            trade_gate["message"] = note
            trade_gate["status"] = "窗口已关闭" if snapshot_status.get("ok") else "闸门关闭"
    mark_to_market(state, quotes)
    if not trade_gate.get("message"):
        trade_gate["message"] = note
    write_outputs(state, ledger, trade_date, note, trade_gate)
    write_snapshots(snapshots)
    save_state(state)

    print(f"Paper trading date: {trade_date}")
    print(f"Equity: {float(state.get('equity', 0.0)):.2f}")
    print(f"Positions: {len(state.get('positions', []))}")
    print(f"Note: {note}")


if __name__ == "__main__":
    main()
