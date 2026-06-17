#!/usr/bin/env python3
"""Build a local static dashboard from candidate CSV data."""

from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from rules_config import screening_config


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "work" / "normalized_data" / "candidates_sample.csv"
DEFAULT_OUTPUT = ROOT / "dashboard" / "index.html"
UNIVERSE_CACHE = ROOT / "work" / "cache" / "stock_universe.csv"
MANUAL_EXPORTS = ROOT / "01_原始资料" / "market_data" / "manual_exports"
NEXT_DAY_REVIEW = ROOT / "work" / "review" / "next_day_review_latest.csv"
PAPER_PERFORMANCE = ROOT / "work" / "paper_trading" / "performance_latest.json"
PAPER_POSITIONS = ROOT / "work" / "paper_trading" / "positions_latest.csv"
PAPER_LEDGER = ROOT / "work" / "paper_trading" / "trade_ledger.csv"
LATEST_MARKET = ROOT / "01_原始资料" / "market_data" / "raw_csv" / "latest_market_data.csv"
CLOUD_REFRESH_ENDPOINT = ROOT / "work" / "cloud" / "refresh_endpoint.txt"
QUOTE_ENDPOINTS = ROOT / "work" / "cloud" / "quote_endpoints.txt"
COVERAGE_BASIC_ROWS = 1500
COVERAGE_FULL_ROWS = 3000
REFRESH_TIMES = ["09:32", "10:30", "11:25", "13:30", "14:15", "14:35", "14:45", "14:52", "14:57", "15:10", "16:10"]


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def num(value: object, default: float = 0.0) -> float:
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def split_tags(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").replace("；", ";").split(";") if item.strip()]


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def read_optional_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    return read_csv(path)


def read_optional_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def read_optional_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    lines = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def quote_endpoint_config() -> List[str]:
    endpoints = []
    for endpoint in read_optional_lines(QUOTE_ENDPOINTS):
        normalized = endpoint.rstrip("/")
        if normalized and normalized not in endpoints:
            endpoints.append(normalized)
    fallback = read_optional_text(CLOUD_REFRESH_ENDPOINT).rstrip("/")
    if fallback and fallback not in endpoints:
        endpoints.append(fallback)
    return endpoints


def market_quotes(path: Path = LATEST_MARKET) -> Dict[str, Dict[str, str]]:
    return {row.get("stock_code", ""): row for row in read_optional_csv(path) if row.get("stock_code")}


def enrich_paper_ledger(ledger: List[Dict[str, str]], quotes: Dict[str, Dict[str, str]]) -> List[Dict[str, str]]:
    enriched = []
    for row in ledger:
        item = dict(row)
        quote = quotes.get(item.get("stock_code", ""))
        latest = quote.get("close", "") if quote else ""
        item["latest_price"] = latest
        if item.get("action") == "BUY" and latest:
            shares = num(item.get("shares"))
            buy_price = num(item.get("price"))
            latest_price = num(latest)
            cost = buy_price * shares
            pnl = round((latest_price - buy_price) * shares, 2)
            item["latest_pnl_amount"] = f"{pnl:.2f}"
            item["latest_pnl_pct"] = f"{(pnl / cost * 100):.2f}" if cost else "0.00"
        else:
            item["latest_pnl_amount"] = item.get("pnl_amount", "")
            item["latest_pnl_pct"] = item.get("pnl_pct", "")
        enriched.append(item)
    return enriched


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return sum(1 for _ in csv.DictReader(file))


def count_manual_exports(path: Path = MANUAL_EXPORTS) -> int:
    if not path.exists():
        return 0
    return sum(
        1
        for item in path.iterdir()
        if item.suffix.lower() in {".csv", ".xlsx", ".xls"} and not item.name.startswith(".")
    )


def coverage_status(cache_rows: int) -> str:
    if cache_rows >= COVERAGE_FULL_ROWS:
        return "接近全量"
    if cache_rows >= COVERAGE_BASIC_ROWS:
        return "基本可用"
    return "覆盖偏窄"


def parse_trade_date(value: str) -> Optional[date]:
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def freshness_info(trade_date: str) -> Dict[str, object]:
    parsed = parse_trade_date(trade_date)
    today = date.today()
    if parsed is None:
        return {
            "freshness_status": "无数据日期",
            "freshness_note": "未识别到交易日，请先刷新数据。",
            "freshness_days": "",
        }
    days = (today - parsed).days
    if days < 0:
        return {
            "freshness_status": "日期异常",
            "freshness_note": f"数据交易日为 {trade_date}，晚于当前日期，请检查本机时间或数据源。",
            "freshness_days": days,
        }
    if days == 0:
        return {
            "freshness_status": "今日数据",
            "freshness_note": f"当前数据交易日为 {trade_date}。",
            "freshness_days": days,
        }
    if days == 1:
        return {
            "freshness_status": "上一自然日数据",
            "freshness_note": f"当前数据交易日为 {trade_date}。如今天已进入盘后或收盘后，请点击刷新确认。",
            "freshness_days": days,
        }
    return {
        "freshness_status": "可能过期",
        "freshness_note": f"当前数据交易日为 {trade_date}，距离今天已有 {days} 天，请优先刷新。",
        "freshness_days": days,
    }


def candidate_rows(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    candidates = [row for row in rows if row.get("pool_level") in {"A", "B", "C"}]
    pool_order = {"A": 0, "B": 1, "C": 2}
    candidates.sort(
        key=lambda row: (
            pool_order.get(row.get("pool_level", ""), 9),
            num(row.get("pool_rank"), 999),
            -num(row.get("candidate_score")),
        )
    )
    return candidates


def raw_candidate_count(rows: Iterable[Dict[str, str]]) -> int:
    return sum(1 for row in rows if row.get("pool_raw_level") in {"A", "B", "C"} or row.get("pool_level") in {"A", "B", "C"})


def excluded_rows(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    return [row for row in rows if row.get("universe_eligible") == "否"]


def theme_counts(rows: Iterable[Dict[str, str]]) -> Counter:
    counts: Counter = Counter()
    for row in rows:
        for tag in split_tags(row.get("theme_tags", "")):
            counts[tag] += 1
    return counts


def pool_counts(rows: Iterable[Dict[str, str]]) -> Dict[str, int]:
    counts = Counter(row.get("pool_level", "") for row in rows)
    return {pool: counts.get(pool, 0) for pool in ("A", "B", "C")}


def source_counts(rows: Iterable[Dict[str, str]]) -> Counter:
    return Counter(row.get("data_source", "未知来源") or "未知来源" for row in rows)


def source_label(source: str) -> str:
    labels = {
        "ths_q_hs_snapshot": "同花顺行情列表",
        "ths_q_hs_snapshot_partial": "同花顺行情列表局部",
        "eastmoney_push2_snapshot": "东方财富行情快照",
        "sina_hq_universe_snapshot": "本地股票池 + 新浪行情",
        "sina_hq_focus_snapshot": "新浪重点样本",
        "akshare_stock_zh_a_spot_em": "AKShare 行情快照",
    }
    if source.startswith("ths_manual_export:"):
        return "同花顺手动导入"
    return labels.get(source, source or "未知来源")


def market_state(candidates: List[Dict[str, str]]) -> str:
    a_count = sum(1 for row in candidates if row.get("pool_level") == "A")
    risk_count = sum(1 for row in candidates if "暂无明显风险" not in row.get("risk_tags", ""))
    if not candidates:
        return "空仓等待"
    if a_count >= 3 and risk_count <= 1:
        return "偏强"
    if a_count >= 1:
        return "可观察"
    return "谨慎"


def recommendation_phase(now: Optional[datetime] = None) -> Dict[str, object]:
    current = (now or datetime.now()).time()
    phases = [
        (time(9, 32), "盘前等待", "等待开盘后第一轮数据，不生成买入建议。", False),
        (time(11, 25), "早盘观察", "识别高开、低开、题材强弱和开盘冲高回落，不建议买入。", False),
        (time(13, 30), "午盘快照", "记录早盘最终强弱，午后继续观察主线是否延续。", False),
        (time(14, 15), "午后观察", "观察午后资金回流和主题延续，不建议直接执行。", False),
        (time(14, 35), "午后预选", "开始锁定候选范围，买入、止盈、止损点位仅作预估。", False),
        (time(14, 45), "尾盘候选", "开始给出尾盘候选和初步执行点位，继续剔除急拉诱多。", False),
        (time(14, 52), "候选收窄", "收窄候选，重点核对量能、收盘位置和风险标签。", False),
        (time(14, 57), "准推荐", "最终确认前版本，用于人工准备和模拟盘候选等待。", False),
        (time(15, 0), "最终推荐", "15:00 前最终推荐窗口，模拟盘仅在 14:57 后按最终名单执行。", True),
        (time(15, 10), "收盘复盘", "不再生成买入建议，记录收盘后复盘快照。", False),
        (time(23, 59, 59), "盘后复盘", "稳定收盘数据复盘，用于次日计划。", False),
    ]
    for end_time, label, note, executable in phases:
        if current < end_time:
            return {
                "label": label,
                "note": note,
                "allows_buy": executable,
                "refresh_times": REFRESH_TIMES,
            }
    return {
        "label": "盘后复盘",
        "note": "稳定收盘数据复盘，用于次日计划。",
        "allows_buy": False,
        "refresh_times": REFRESH_TIMES,
    }


def to_dashboard_data(rows: List[Dict[str, str]], source: Path) -> Dict[str, object]:
    candidates = candidate_rows(rows)
    excluded = excluded_rows(rows)
    pools = pool_counts(candidates)
    themes = theme_counts(candidates)
    sources = source_counts(rows)
    primary_source = sources.most_common(1)[0][0] if sources else ""
    trade_dates = sorted({row.get("trade_date", "") for row in rows if row.get("trade_date")})
    trade_date = trade_dates[-1] if trade_dates else ""
    freshness = freshness_info(trade_date)
    cache_rows = count_csv_rows(UNIVERSE_CACHE)
    config = screening_config()
    quotes = market_quotes()
    ledger = read_optional_csv(PAPER_LEDGER)[-80:]
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(source),
        "primary_source": source_label(primary_source),
        "source_counts": [(source_label(name), count) for name, count in sources.most_common()],
        "trade_date": trade_date,
        **freshness,
        "market_state": market_state(candidates),
        "recommendation_phase": recommendation_phase(),
        "summary": {
            "total_rows": len(rows),
            "eligible": sum(1 for row in rows if row.get("universe_eligible") == "是"),
            "excluded": len(excluded),
            "raw_candidate_count": raw_candidate_count(rows),
            "candidate_count": len(candidates),
            "a_pool": pools["A"],
            "b_pool": pools["B"],
            "c_pool": pools["C"],
            "universe_cache": cache_rows,
            "coverage_status": coverage_status(cache_rows),
            "manual_exports": count_manual_exports(),
            "defense_mode": config.get("defense_mode", {}),
        },
        "theme_counts": themes.most_common(),
        "config": config,
        "cloud_refresh_endpoint": read_optional_text(CLOUD_REFRESH_ENDPOINT),
        "quote_endpoints": quote_endpoint_config(),
        "candidates": candidates,
        "excluded": excluded,
        "next_day_review": read_optional_csv(NEXT_DAY_REVIEW),
        "paper_trading": {
            "performance": read_optional_json(PAPER_PERFORMANCE),
            "positions": read_optional_csv(PAPER_POSITIONS),
            "ledger": enrich_paper_ledger(ledger, quotes),
        },
    }


def build_html(data: Dict[str, object]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    script_payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A股短线助手看板</title>
  <style>
    :root {{
      --bg: #f4f6f8;
      --panel: #ffffff;
      --ink: #18202a;
      --muted: #657386;
      --line: #dfe5ec;
      --red: #c93434;
      --blue: #2568a8;
      --teal: #0f766e;
      --green: #16834f;
      --amber: #aa6509;
      --purple: #7357a6;
      --shadow: 0 8px 24px rgba(20, 32, 46, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.5;
    }}
    button, input {{ font: inherit; }}
    .shell {{ min-height: 100vh; }}
    .topbar {{
      background: #101820;
      color: #fff;
      border-bottom: 4px solid #c93434;
    }}
    .topbar-inner {{
      max-width: 1320px;
      margin: 0 auto;
      padding: 20px 22px 18px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
      align-items: end;
    }}
    h1 {{
      margin: 0;
      font-size: 30px;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin-top: 6px;
      color: #c7d0dc;
      font-size: 14px;
    }}
    .status-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      height: 40px;
      padding: 0 14px;
      border: 1px solid rgba(255,255,255,.18);
      border-radius: 8px;
      background: rgba(255,255,255,.08);
      white-space: nowrap;
    }}
    .top-actions {{
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
      align-items: center;
    }}
    .refresh-button {{
      height: 40px;
      border: 1px solid rgba(255,255,255,.22);
      border-radius: 8px;
      padding: 0 14px;
      color: #fff;
      background: #c93434;
      cursor: pointer;
      font-weight: 700;
    }}
    .refresh-button:disabled {{
      opacity: .7;
      cursor: wait;
    }}
    .refresh-state {{
      min-width: 112px;
      color: #c7d0dc;
      font-size: 13px;
      text-align: right;
    }}
    .status-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #48c989;
    }}
    main {{
      max-width: 1320px;
      margin: 0 auto;
      padding: 18px 22px 44px;
    }}
    .notice {{
      display: none;
    }}
    .refresh-summary {{
      display: none;
      background: #eef8f5;
      border: 1px solid #b9d8d1;
      color: #174a43;
      border-radius: 8px;
      padding: 10px 12px;
      margin-bottom: 14px;
      font-size: 14px;
    }}
    .refresh-summary.show {{ display: block; }}
    .freshness-banner {{
      display: none;
      background: #eef4fb;
      border: 1px solid #bdd0e8;
      color: #183f68;
      border-radius: 8px;
      padding: 10px 12px;
      margin-bottom: 14px;
      font-size: 14px;
    }}
    .freshness-banner.show {{ display: block; }}
    .freshness-banner.warn {{
      background: #fff8ec;
      border-color: #e5c486;
      color: #6a4306;
    }}
    .risk-alerts {{
      display: none;
      margin-bottom: 12px;
      border: 1px solid #efc8c8;
      border-left: 5px solid var(--red);
      border-radius: 8px;
      background: #fff5f5;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .risk-alerts.show {{
      display: block;
    }}
    .risk-alert {{
      padding: 10px 12px;
      border-bottom: 1px solid #f3d6d6;
      color: #6f1d1d;
    }}
    .risk-alert:last-child {{
      border-bottom: 0;
    }}
    .risk-alert strong {{
      display: block;
      font-size: 14px;
      line-height: 1.25;
    }}
    .risk-alert span {{
      display: block;
      margin-top: 3px;
      color: #8f2a2a;
      font-size: 12px;
      line-height: 1.35;
    }}
    .risk-alert.extra {{
      border-left: 5px solid var(--amber);
      background: #fff8ec;
      color: #6a4306;
    }}
    .focus-realtime {{
      display: none;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 12px;
      margin-bottom: 14px;
    }}
    .focus-realtime.show {{
      display: block;
    }}
    .focus-realtime-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 10px;
    }}
    .focus-realtime-head h2 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
    }}
    .focus-realtime-meta {{
      color: var(--muted);
      font-size: 12px;
      text-align: right;
    }}
    .sound-toggle {{
      height: 32px;
      border: 1px solid #c9d6e4;
      border-radius: 8px;
      background: #f8fafc;
      color: #163e62;
      padding: 0 10px;
      cursor: pointer;
      font-weight: 700;
      white-space: nowrap;
    }}
    .sound-toggle.active {{
      border-color: var(--teal);
      background: #edf9f6;
      color: var(--teal);
    }}
    .focus-price-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 8px;
    }}
    .focus-price-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fafbfc;
      padding: 9px;
      min-width: 0;
    }}
    .focus-price-card.alert {{
      border-color: #efc8c8;
      background: #fff7f7;
    }}
    .focus-price-card.strong {{
      border-color: #e5c486;
      background: #fffaf0;
    }}
    .focus-price-card strong {{
      display: block;
      font-size: 13px;
      line-height: 1.25;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .focus-price-card .price {{
      display: block;
      margin-top: 4px;
      font-size: 20px;
      line-height: 1.1;
      font-weight: 800;
      color: var(--ink);
    }}
    .focus-price-card .price.up {{
      color: var(--red);
    }}
    .focus-price-card .price.down {{
      color: var(--green);
    }}
    .focus-price-card span {{
      display: block;
      margin-top: 3px;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.35;
    }}
    .position-badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      margin-bottom: 5px;
    }}
    .position-badge {{
      display: inline-flex;
      align-items: center;
      min-height: 20px;
      border: 1px solid #c9d6e4;
      border-radius: 999px;
      background: #eef5fc;
      color: #163e62;
      padding: 0 7px;
      font-size: 11px;
      font-weight: 800;
      line-height: 1;
    }}
    .position-badge.strong {{
      border-color: #e5c486;
      background: #fff4d6;
      color: #7a4a05;
    }}
    .funnel {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }}
    .funnel-step {{
      position: relative;
      min-height: 64px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .funnel-step::after {{
      content: "";
      position: absolute;
      top: 0;
      right: 0;
      width: 5px;
      height: 100%;
      background: var(--blue);
    }}
    .funnel-step:nth-child(2)::after {{ background: var(--teal); }}
    .funnel-step:nth-child(3)::after {{ background: var(--purple); }}
    .funnel-step:nth-child(4)::after {{ background: var(--red); }}
    .funnel-step span {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
    }}
    .funnel-step strong {{
      display: block;
      margin-top: 3px;
      font-size: 22px;
      line-height: 1.1;
    }}
    .funnel-step small {{
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.3;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 14px;
    }}
    .metric {{
      position: relative;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 10px;
      min-height: 58px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .metric.clickable {{
      cursor: pointer;
      transition: transform .12s ease, border-color .12s ease, box-shadow .12s ease;
    }}
    .metric.clickable:hover {{
      transform: translateY(-1px);
      border-color: #b8c7d8;
      box-shadow: 0 10px 26px rgba(20, 32, 46, 0.12);
    }}
    .metric.active-filter {{
      border-color: #101820;
      box-shadow: inset 0 0 0 2px #101820, var(--shadow);
    }}
    .metric span {{
      color: var(--muted);
      display: block;
      font-size: 11px;
      font-weight: 700;
      line-height: 1.25;
    }}
    .metric strong {{
      margin-top: 3px;
      display: block;
      font-size: clamp(18px, 1.25vw, 24px);
      line-height: 1.12;
      overflow-wrap: anywhere;
      word-break: break-word;
      letter-spacing: 0;
    }}
    .metric.long strong {{
      font-size: clamp(15px, 1vw, 20px);
      line-height: 1.16;
    }}
    .metric.small strong {{
      font-size: clamp(13px, .9vw, 17px);
      line-height: 1.18;
    }}
    .metric.a strong {{ color: var(--red); }}
    .metric.b strong {{ color: var(--blue); }}
    .metric.c strong {{ color: var(--teal); }}
    .note-corner {{
      position: absolute;
      top: 0;
      right: 0;
      width: 24px;
      height: 24px;
      border: 0;
      padding: 0;
      background: transparent;
      cursor: pointer;
    }}
    .note-corner::before {{
      content: "";
      position: absolute;
      top: 0;
      right: 0;
      width: 0;
      height: 0;
      border-top: 18px solid var(--red);
      border-left: 18px solid transparent;
      border-top-right-radius: 7px;
    }}
    .note-popup {{
      display: none;
      position: absolute;
      z-index: 5;
      top: 28px;
      right: 8px;
      width: min(260px, 75vw);
      padding: 10px;
      border: 1px solid #efc8c8;
      border-radius: 8px;
      background: #fff8f8;
      color: #6f1d1d;
      box-shadow: var(--shadow);
      font-size: 12px;
      line-height: 1.45;
    }}
    .metric.show-note .note-popup {{
      display: block;
    }}
    .paper-hero {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 12px;
      margin-bottom: 14px;
    }}
    .paper-hero-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
      margin-bottom: 8px;
    }}
    .paper-hero-head h2 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
    }}
    .paper-hero-head span {{
      color: var(--muted);
      font-size: 12px;
      text-align: right;
    }}
    .paper-hero .paper-panel {{
      margin-top: 0;
    }}
    .paper-hero .paper-metrics {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
    .paper-actions, .detail-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .paper-detail-button, .detail-button {{
      height: 34px;
      border: 1px solid #c9d6e4;
      border-radius: 8px;
      background: #f8fafc;
      color: #163e62;
      padding: 0 12px;
      font-weight: 700;
      cursor: pointer;
    }}
    .paper-detail-button:hover, .detail-button:hover {{
      border-color: var(--blue);
      background: #eef5fc;
    }}
    .layout {{
      display: block;
    }}
    .board {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    .board h2 {{
      margin: 0;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .board-tools {{
      display: grid;
      grid-template-columns: minmax(260px, 1fr);
      gap: 12px;
      padding: 14px 14px 0;
      align-items: start;
    }}
    .tool-panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fafbfc;
      padding: 10px;
      min-width: 0;
    }}
    .tool-panel .label {{
      margin-bottom: 7px;
    }}
    .control-group {{
      margin-top: 14px;
      border-top: 1px solid var(--line);
      padding-top: 14px;
    }}
    .segmented {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px;
      margin-top: 10px;
    }}
    .segmented button {{
      border: 1px solid var(--line);
      background: #f7f8fa;
      border-radius: 8px;
      padding: 8px 0;
      cursor: pointer;
    }}
    .segmented button.active {{
      background: #101820;
      color: #fff;
      border-color: #101820;
    }}
    .search {{
      width: 100%;
      height: 38px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0 10px;
      background: #fff;
    }}
    .theme-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }}
    .theme-chip {{
      border: 1px solid #cad5e3;
      background: #f6f9fc;
      border-radius: 999px;
      padding: 5px 9px;
      font-size: 12px;
      cursor: pointer;
    }}
    .theme-chip.active {{
      background: #e8f1fb;
      border-color: var(--blue);
      color: #174b80;
    }}
    .board-header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 14px 14px 0;
    }}
    .board-subtitle {{
      color: var(--muted);
      font-size: 13px;
      margin-top: 3px;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      padding: 14px;
    }}
    .candidate {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }}
    .candidate-head {{
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 10px;
      align-items: center;
      padding: 12px;
      border-bottom: 1px solid var(--line);
    }}
    .pool {{
      width: 88px;
      height: 40px;
      border-radius: 8px;
      color: #fff;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 12px;
      background: var(--red);
    }}
    .pool.B {{ background: var(--blue); }}
    .pool.C {{ background: var(--teal); }}
    .name {{
      font-size: 20px;
      font-weight: 800;
      line-height: 1.1;
    }}
    .code {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 3px;
    }}
    .change {{
      font-size: 22px;
      font-weight: 800;
      color: var(--red);
      white-space: nowrap;
    }}
    .candidate-body {{
      padding: 12px;
    }}
    .live-price-line {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      border: 1px solid #f0c9c9;
      border-radius: 8px;
      background: #fff8f8;
      padding: 8px 10px;
      margin-bottom: 10px;
      color: #8f2a2a;
      font-size: 12px;
      font-weight: 800;
    }}
    .live-price-line strong {{
      color: var(--red);
      font-size: 18px;
      line-height: 1.1;
    }}
    .live-price-line strong.down {{
      color: var(--green);
    }}
    .scoreline {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 10px;
    }}
    .score-pill {{
      border: 1px solid var(--line);
      background: #fbfbfc;
      border-radius: 999px;
      padding: 4px 9px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .point-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin: 0 0 10px;
    }}
    .point {{
      border: 1px solid #f0c9c9;
      background: #fff8f8;
      border-radius: 8px;
      padding: 8px 10px;
      min-width: 0;
    }}
    .point span {{
      display: block;
      color: #8f2a2a;
      font-size: 12px;
      font-weight: 800;
      line-height: 1.2;
    }}
    .point strong {{
      display: block;
      margin-top: 3px;
      color: var(--red);
      font-size: 18px;
      line-height: 1.1;
      letter-spacing: 0;
      overflow-wrap: anywhere;
    }}
    .point.stop {{
      border-color: #d8dde5;
      background: #f8fafc;
    }}
    .point.stop span {{
      color: var(--muted);
    }}
    .point.stop strong {{
      color: var(--ink);
    }}
    .point.follow {{
      border-color: #cfe2de;
      background: #f2fbf8;
    }}
    .point.follow span {{
      color: var(--teal);
    }}
    .point.follow strong {{
      color: var(--teal);
      font-size: 13px;
      line-height: 1.25;
    }}
    .tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 10px;
    }}
    .tag {{
      border: 1px solid #cdd8e5;
      background: #f3f7fb;
      color: #244762;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
    }}
    .tag.strategy {{
      background: #fff1f1;
      color: #9e2525;
      border-color: #efc8c8;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 10px;
    }}
    .stat {{
      padding: 8px;
      border-right: 1px solid var(--line);
      background: #fafbfc;
    }}
    .stat:last-child {{ border-right: 0; }}
    .stat span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
    }}
    .stat strong {{
      display: block;
      margin-top: 2px;
      font-size: 15px;
    }}
    .reason, .risk, .score-detail, .plan {{
      border-left: 4px solid var(--blue);
      background: #f7fbff;
      border-radius: 6px;
      padding: 9px 10px;
      margin-top: 8px;
    }}
    .workflow {{
      border-left: 4px solid var(--teal);
      background: #f2fbf8;
      border-radius: 6px;
      padding: 9px 10px;
      margin-top: 8px;
    }}
    .workflow-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
      margin-top: 6px;
    }}
    .workflow-grid div {{
      border: 1px solid #cfe2de;
      border-radius: 8px;
      background: #fbfffd;
      padding: 7px;
      font-size: 12px;
      min-width: 0;
    }}
    .workflow-grid strong {{
      display: block;
      color: var(--ink);
      font-size: 12px;
      margin-bottom: 2px;
    }}
    .workflow-grid p {{
      margin: 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .risk.ok {{
      border-left-color: var(--green);
      background: #f2fbf6;
    }}
    .risk.warn {{
      border-left-color: var(--amber);
      background: #fff8ec;
    }}
    .score-detail {{
      border-left-color: var(--purple);
      background: #f7f4fb;
    }}
    .label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 3px;
    }}
    .plan-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin-top: 8px;
    }}
    .plan-grid div {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      background: #fbfbfc;
      font-size: 13px;
    }}
    .themes-panel {{
      display: grid;
      gap: 9px;
      margin-top: 10px;
    }}
    .theme-row {{
      display: grid;
      grid-template-columns: 70px 1fr 24px;
      gap: 8px;
      align-items: center;
      font-size: 13px;
    }}
    .config-panel {{
      display: grid;
      gap: 8px;
      margin-top: 10px;
      font-size: 13px;
    }}
    .workflow-panel {{
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }}
    .review-panel {{
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }}
    .review-row {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fafbfc;
      padding: 8px;
      font-size: 12px;
    }}
    .review-row strong {{
      display: block;
      font-size: 13px;
      color: var(--ink);
    }}
    .review-row span {{
      color: var(--muted);
    }}
    .review-row em {{
      display: block;
      margin-top: 3px;
      color: var(--teal);
      font-style: normal;
      font-weight: 700;
      line-height: 1.35;
    }}
    .review-row.weak em {{
      color: var(--amber);
    }}
    .paper-panel {{
      display: grid;
      gap: 8px;
      margin-top: 10px;
      font-size: 12px;
    }}
    .paper-metrics {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px;
    }}
    .paper-metric, .paper-position, .paper-trade {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fafbfc;
      padding: 8px;
      min-width: 0;
    }}
    .paper-metric span, .paper-position span, .paper-trade span {{
      display: block;
      color: var(--muted);
      line-height: 1.3;
    }}
    .paper-metric strong {{
      display: block;
      margin-top: 2px;
      font-size: 15px;
      color: var(--ink);
      overflow-wrap: anywhere;
    }}
    .paper-metric.profit strong {{
      color: var(--red);
    }}
    .paper-metric.loss strong {{
      color: var(--green);
    }}
    .paper-position strong, .paper-trade strong {{
      display: block;
      color: var(--ink);
      font-size: 13px;
      line-height: 1.25;
    }}
    .paper-position em, .paper-trade em {{
      display: block;
      margin-top: 3px;
      color: var(--red);
      font-style: normal;
      font-weight: 700;
    }}
    .paper-position.weak em, .paper-trade.weak em {{
      color: var(--green);
    }}
    .paper-note {{
      color: var(--muted);
      line-height: 1.4;
    }}
    .detail-page {{
      position: fixed;
      inset: 0;
      z-index: 50;
      display: none;
      background: var(--bg);
      color: var(--ink);
      overflow: auto;
    }}
    .detail-page.show {{
      display: block;
    }}
    .detail-topbar {{
      position: sticky;
      top: 0;
      z-index: 2;
      background: #101820;
      color: #fff;
      border-bottom: 4px solid var(--red);
    }}
    .detail-topbar-inner {{
      max-width: 980px;
      margin: 0 auto;
      padding: 12px;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
    }}
    .detail-topbar h2 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.25;
    }}
    .back-button {{
      height: 36px;
      border: 1px solid rgba(255,255,255,.3);
      border-radius: 8px;
      background: rgba(255,255,255,.08);
      color: #fff;
      padding: 0 12px;
      cursor: pointer;
      white-space: nowrap;
    }}
    .detail-content {{
      max-width: 980px;
      margin: 0 auto;
      padding: 14px 12px 36px;
    }}
    .detail-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      box-shadow: var(--shadow);
      padding: 12px;
      margin-bottom: 12px;
    }}
    .detail-card h3 {{
      margin: 0 0 8px;
      font-size: 16px;
      line-height: 1.3;
    }}
    .detail-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.65;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    .detail-list {{
      display: grid;
      gap: 8px;
    }}
    .detail-row {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fafbfc;
      padding: 10px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: center;
    }}
    .detail-row strong {{
      display: block;
      font-size: 14px;
      line-height: 1.25;
    }}
    .detail-row span {{
      display: block;
      margin-top: 3px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}
    .detail-row em {{
      font-style: normal;
      font-weight: 800;
      color: var(--red);
      text-align: right;
      white-space: nowrap;
    }}
    .detail-row.weak em {{
      color: var(--green);
    }}
    .paper-ledger-grid {{
      display: grid;
      gap: 12px;
    }}
    .paper-filter-bar {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 8px;
      align-items: end;
    }}
    .paper-filter-bar label {{
      display: grid;
      gap: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .paper-filter-bar input, .paper-filter-bar select {{
      width: 100%;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      padding: 0 8px;
      font: inherit;
    }}
    .paper-summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }}
    .paper-summary-item {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fafbfc;
      padding: 10px;
      min-width: 0;
    }}
    .paper-summary-item span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
    }}
    .paper-summary-item strong {{
      display: block;
      margin-top: 3px;
      color: var(--ink);
      font-size: 16px;
      overflow-wrap: anywhere;
    }}
    .paper-summary-item.profit strong, .profit-text {{
      color: var(--red);
    }}
    .paper-summary-item.loss strong, .loss-text {{
      color: var(--green);
    }}
    .paper-table-wrap {{
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .paper-table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 860px;
      background: #fff;
      font-size: 12px;
    }}
    .paper-table th, .paper-table td {{
      padding: 9px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }}
    .paper-table th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: #f1f5f9;
      color: #405065;
      font-weight: 800;
    }}
    .paper-table tbody tr:last-child td {{
      border-bottom: 0;
    }}
    .paper-table .note-cell {{
      max-width: 280px;
      white-space: normal;
      color: var(--muted);
      line-height: 1.35;
    }}
    .action-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 44px;
      height: 24px;
      border-radius: 999px;
      font-weight: 800;
      border: 1px solid #c9d6e4;
      background: #eef5fc;
      color: #163e62;
    }}
    .action-badge.sell {{
      border-color: #d1d5db;
      background: #f3f4f6;
      color: #374151;
    }}
    .calendar-toolbar {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 10px;
      margin: 4px 0 12px;
      flex-wrap: wrap;
    }}
    .calendar-toolbar label {{
      display: grid;
      gap: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }}
    .calendar-toolbar input {{
      min-width: 150px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      font: inherit;
      color: var(--ink);
      background: #fff;
    }}
    .calendar-legend {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .calendar-grid {{
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 6px;
    }}
    .calendar-head {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-align: center;
    }}
    .calendar-day {{
      min-height: 68px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fafbfc;
      padding: 7px;
      display: grid;
      align-content: start;
      gap: 4px;
      cursor: pointer;
    }}
    .calendar-day.empty {{
      background: transparent;
      border-color: transparent;
      cursor: default;
    }}
    .calendar-day.closed {{
      background: #f1f5f9;
      border-color: #d8e0ea;
      color: #7b8794;
    }}
    .calendar-day.closed strong {{
      color: #5f6b7a;
    }}
    .calendar-day.today {{
      border-color: var(--blue);
      box-shadow: inset 0 0 0 1px var(--blue);
    }}
    .calendar-day.profit {{
      background: #fff5f5;
      border-color: #efc8c8;
    }}
    .calendar-day.loss {{
      background: #f0fdf4;
      border-color: #bbf7d0;
    }}
    .calendar-day.closed.profit, .calendar-day.closed.loss {{
      background: #f1f5f9;
      border-color: #cbd5e1;
    }}
    .calendar-day strong {{
      font-size: 13px;
    }}
    .calendar-day span {{
      display: block;
      font-size: 12px;
      font-weight: 800;
    }}
    .calendar-day em {{
      color: var(--muted);
      font-size: 11px;
      font-style: normal;
    }}
    body.detail-open {{
      overflow: hidden;
    }}
    .workflow-step {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fafbfc;
      padding: 8px;
    }}
    .workflow-step strong {{
      display: block;
      font-size: 13px;
      margin-bottom: 3px;
    }}
    .workflow-step span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}
    .config-line {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fafbfc;
      padding: 8px;
    }}
    .config-line span {{
      color: var(--muted);
    }}
    .config-line strong {{
      text-align: right;
    }}
    .config-tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .config-warning {{
      border-left: 4px solid var(--amber);
      background: #fff8ec;
      border-radius: 6px;
      padding: 8px;
      color: #714503;
      font-size: 12px;
    }}
    .bar {{
      height: 8px;
      background: #edf1f5;
      border-radius: 999px;
      overflow: hidden;
    }}
    .bar span {{
      display: block;
      height: 100%;
      background: var(--purple);
    }}
    .excluded {{
      padding: 0 14px 14px;
    }}
    .excluded details {{
      border-top: 1px solid var(--line);
      padding-top: 12px;
      color: var(--muted);
    }}
    .excluded li {{
      margin: 5px 0;
    }}
    .empty {{
      padding: 28px;
      color: var(--muted);
      text-align: center;
    }}
    @media (max-width: 980px) {{
      .topbar-inner {{ grid-template-columns: 1fr; align-items: start; }}
      .funnel {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .metrics {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .point-grid {{ grid-template-columns: 1fr; }}
      .workflow-grid {{ grid-template-columns: 1fr; }}
      .board-tools {{ grid-template-columns: 1fr; }}
      .cards {{ grid-template-columns: 1fr; }}
      .paper-hero .paper-metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .focus-price-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .paper-filter-bar {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .paper-summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .detail-row {{ grid-template-columns: 1fr; }}
      .detail-row em {{ text-align: left; }}
    }}
    @media (max-width: 620px) {{
      main {{ padding: 14px 12px 34px; }}
      .topbar-inner {{ padding: 18px 12px; }}
      h1 {{ font-size: 24px; }}
      .top-actions {{ justify-content: flex-start; }}
      .funnel {{ grid-template-columns: 1fr; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .paper-hero-head {{ display: block; }}
      .paper-hero-head span {{ display: block; margin-top: 4px; text-align: left; }}
      .focus-realtime-head {{ display: block; }}
      .focus-realtime-meta {{ margin-top: 8px; text-align: left; }}
      .focus-price-grid {{ grid-template-columns: 1fr; }}
      .paper-hero .paper-metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .paper-metric strong {{ font-size: 14px; }}
      .paper-filter-bar {{ grid-template-columns: 1fr; }}
      .paper-summary-grid {{ grid-template-columns: 1fr; }}
      .calendar-grid {{ gap: 4px; }}
      .calendar-toolbar {{ align-items: stretch; }}
      .calendar-toolbar label, .calendar-toolbar input {{ width: 100%; }}
      .calendar-day {{ min-height: 58px; padding: 5px; }}
      .candidate-head {{ grid-template-columns: 1fr auto; }}
      .pool {{ width: auto; height: 32px; padding: 0 10px; grid-column: 1 / -1; }}
      .change {{ font-size: 20px; }}
      .stats, .plan-grid {{ grid-template-columns: 1fr; }}
      .stat {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .stat:last-child {{ border-bottom: 0; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="topbar-inner">
        <div>
          <h1>A股短线助手看板</h1>
          <div class="subtitle" id="subtitle"></div>
        </div>
        <div class="top-actions">
          <div class="status-pill"><span class="status-dot"></span><span id="marketState"></span></div>
          <button class="refresh-button" id="refreshData" type="button">刷新数据</button>
          <div class="refresh-state" id="refreshState"></div>
        </div>
      </div>
    </header>
    <main>
      <div class="notice">本看板用于盘后候选池整理和复盘辅助，不构成投资建议。重点看入选原因、风险标签和次日验证条件。</div>
      <div class="refresh-summary" id="refreshSummary"></div>
      <div class="freshness-banner" id="freshnessBanner"></div>
      <section class="risk-alerts" id="riskAlerts"></section>
      <section class="focus-realtime" id="focusRealtime"></section>
      <section class="funnel" id="screeningFunnel"></section>
      <section class="metrics" id="metrics"></section>
      <section class="paper-hero">
        <div class="paper-hero-head">
          <h2>模拟盘</h2>
      <span>本金 1,000,000 元 · 重点关注平均买入 · 严格 T+1 · 14:57 尾盘执行</span>
        </div>
        <div class="paper-panel" id="paperTradingHero"></div>
      </section>
      <section class="layout">
        <section class="board">
          <div class="board-header">
            <div>
              <h2>候选池</h2>
              <div class="board-subtitle" id="resultCount"></div>
            </div>
          </div>
          <div class="board-tools">
            <div class="tool-panel">
              <span class="label">搜索</span>
              <input id="search" class="search" placeholder="搜索代码、名称、主题">
            </div>
          </div>
          <div class="cards" id="cards"></div>
          <div class="excluded" id="excluded"></div>
        </section>
      </section>
    </main>
  </div>
  <section class="detail-page" id="detailPage" aria-hidden="true">
    <div class="detail-topbar">
      <div class="detail-topbar-inner">
        <h2 id="detailTitle">详情</h2>
        <button class="back-button" id="detailBack" type="button">返回主看板</button>
      </div>
    </div>
    <div class="detail-content" id="detailContent"></div>
  </section>
  <script id="dashboard-data" type="application/json">{script_payload}</script>
  <script>
    const data = JSON.parse(document.getElementById('dashboard-data').textContent);
    data.candidates.forEach((row, index) => row.__idx = index);
    const state = {{ pool: 'ALL', theme: 'ALL', query: '' }};
    const liveState = {{
      quotes: {{}},
      lastUpdated: '',
      quoteEndpoint: '',
      quoteSource: '',
      soundEnabled: false,
      alerted: new Set(),
      paper: null,
      timer: null
    }};

    const poolLabel = {{ A: '重点关注', B: '观察候补', C: '题材异动记录' }};
    const poolNotes = {{
      A: '重点关注：命中攻击型尾盘突破或主线热点回流等较强信号，并且严重风险较少，是次日优先观察对象。',
      B: '观察候补：主题或形态有机会，但强度、确认度、风险控制不如重点关注，需要等待次日确认。',
      C: '题材异动记录：命中重点主题，但暂时没有明确策略信号或强度不足，主要用于记录和后续观察。'
    }};
    const metricItems = [
      {{ label: '交易日', value: data.trade_date || '-' }},
      {{ label: '重点关注', value: data.summary.a_pool, tone: 'a', pool: 'A' }},
      {{ label: '观察候补', value: data.summary.b_pool, tone: 'b', pool: 'B' }},
      {{ label: '题材异动记录', value: data.summary.c_pool, tone: 'c', pool: 'C' }},
      {{ label: '推荐阶段', value: data.recommendation_phase?.label || '-' }},
      {{ label: '股票池缓存', value: data.summary.universe_cache }},
      {{ label: '覆盖状态', value: data.summary.coverage_status }},
      {{ label: '已剔除', value: data.summary.excluded }}
    ];

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, char => ({{
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }}[char]));
    }}

    function splitTags(value) {{
      return String(value || '').replace(/；/g, ';').split(';').map(x => x.trim()).filter(Boolean);
    }}

    function numberValue(value) {{
      const n = Number(String(value ?? '').replace(/,/g, ''));
      return Number.isFinite(n) ? n : 0;
    }}

    function money(value) {{
      return numberValue(value).toLocaleString('zh-CN', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
    }}

    function pct(value) {{
      return `${{numberValue(value).toFixed(2)}}%`;
    }}

    function focusRows() {{
      return data.candidates.filter(row => row.pool_level === 'A');
    }}

    function paperStorageKey() {{
      const paper = data.paper_trading || {{}};
      const positions = paper.positions || [];
      const signature = positions.map(row => `${{row.stock_code}}:${{row.entry_date}}:${{row.shares}}`).join('|');
      return `paperRuntime:${{data.trade_date || 'unknown'}}:${{signature || 'empty'}}`;
    }}

    function buildPaperRuntime() {{
      const paper = data.paper_trading || {{}};
      const perf = paper.performance || {{}};
      const positions = (paper.positions || []).map(row => ({{
        ...row,
        shares: numberValue(row.shares),
        remaining_shares: numberValue(row.remaining_shares || row.shares),
        entry_price: numberValue(row.entry_price),
        current_price: numberValue(row.current_price || row.entry_price),
        first_take_profit_point: numberValue(row.first_take_profit_point),
        defensive_stop_point: numberValue(row.defensive_stop_point),
        first_take_done: row.first_take_done === true || row.first_take_done === 'True' || row.first_take_done === 'true' || row.first_take_done === '是',
        live_status: '等待实时行情'
      }}));
      return {{
        trade_date: data.trade_date || '',
        initialized_at: data.generated_at || '',
        initial_capital: numberValue(perf.initial_capital || 1000000),
        cash: numberValue(perf.cash),
        realized_pnl: numberValue(perf.realized_pnl),
        positions,
        ledger: (paper.ledger || []).map(row => ({{ ...row }})),
        last_live_updated: '',
        note: perf.note || ''
      }};
    }}

    function getPaperRuntime() {{
      if (liveState.paper) return liveState.paper;
      try {{
        const stored = JSON.parse(localStorage.getItem(paperStorageKey()) || 'null');
        if (stored && Array.isArray(stored.positions) && Array.isArray(stored.ledger)) {{
          liveState.paper = stored;
          return liveState.paper;
        }}
      }} catch (error) {{}}
      liveState.paper = buildPaperRuntime();
      return liveState.paper;
    }}

    function savePaperRuntime() {{
      try {{
        localStorage.setItem(paperStorageKey(), JSON.stringify(getPaperRuntime()));
      }} catch (error) {{}}
    }}

    function quoteCodes() {{
      const codes = new Set();
      focusRows().forEach(row => codes.add(row.stock_code));
      getPaperRuntime().positions.forEach(row => {{
        if (numberValue(row.remaining_shares) > 0 && row.stock_code) codes.add(row.stock_code);
      }});
      return Array.from(codes).filter(Boolean);
    }}

    function displayPrice(row) {{
      const quote = liveState.quotes[row.stock_code] || {{}};
      return numberValue(quote.price || row.close || row.buy_point);
    }}

    function priceTone(row) {{
      const price = displayPrice(row);
      const base = numberValue(row.buy_point || row.close);
      if (!price || !base) return '';
      if (price > base) return 'up';
      if (price < base) return 'down';
      return '';
    }}

    function quoteEndpoints() {{
      const configured = Array.isArray(data.quote_endpoints) ? data.quote_endpoints : [];
      const fallback = data.cloud_refresh_endpoint ? [data.cloud_refresh_endpoint] : [];
      const seen = new Set();
      return configured.concat(fallback)
        .map(endpoint => String(endpoint || '').trim().replace(/\/$/, ''))
        .filter(endpoint => {{
          if (!endpoint || seen.has(endpoint)) return false;
          seen.add(endpoint);
          return true;
        }});
    }}

    function quoteUrl(endpoint) {{
      return `${{endpoint.replace(/\/$/, '')}}/quotes`;
    }}

    function quoteSourceLabel(endpoint) {{
      if (!endpoint) return '';
      try {{
        const host = new URL(endpoint).hostname;
        if (host.includes('alexsheng666.com')) return '专属域名行情';
        if (host.includes('workers.dev')) return 'Worker行情通道';
        return host;
      }} catch (error) {{
        return '行情通道';
      }}
    }}

    function strongUpsideCandidate(row, price) {{
      const take = numberValue(row.first_take_profit_point || row.sell_point);
      if (!take || price < take) return false;
      const score = numberValue(row.candidate_score);
      const themeLimitUps = numberValue(row.real_theme_limit_up_count || row.theme_limit_up_count);
      const closePosition = numberValue(row.close_position_pct);
      const volumeRatio = numberValue(row.volume_ratio);
      const cleanRisk = !hasMeaningfulRisk(row.risk_tags);
      return score >= 120 && themeLimitUps >= 3 && closePosition >= 97 && volumeRatio >= 1.2 && cleanRisk;
    }}

    function candidateByCode(code) {{
      return data.candidates.find(row => row.stock_code === code) || {{}};
    }}

    function dynamicStopPoint(entry, price, baseStop) {{
      if (!entry || !price) return baseStop;
      const profitPct = (price - entry) / entry * 100;
      let stop = baseStop || entry * 0.98;
      if (profitPct >= 8) stop = Math.max(stop, price * 0.965, entry * 1.03);
      else if (profitPct >= 5) stop = Math.max(stop, price * 0.97, entry * 1.015);
      else if (profitPct >= 2) stop = Math.max(stop, entry * 1.002);
      return Number(stop.toFixed(2));
    }}

    function paperRiskRows() {{
      const snapshot = paperSnapshot();
      return (snapshot.positions || []).map(position => {{
        const quote = liveState.quotes[position.stock_code] || {{}};
        const candidate = candidateByCode(position.stock_code);
        const entry = numberValue(position.entry_price);
        const price = numberValue(quote.price || position.current_price || entry);
        const take = numberValue(position.first_take_profit_point || candidate.first_take_profit_point || candidate.sell_point || (entry ? entry * 1.02 : 0));
        const baseStop = numberValue(position.defensive_stop_point || candidate.defensive_stop_point || candidate.stop_point || (entry ? entry * 0.98 : 0));
        const dynamicStop = dynamicStopPoint(entry, price, baseStop);
        const profitPct = entry ? Number(((price - entry) / entry * 100).toFixed(2)) : 0;
        const dailyPct = numberValue(quote.pct_change);
        const firstTakeDone = position.first_take_done === true || position.first_take_done === 'true' || position.first_take_done === 'True' || position.first_take_done === '是';
        const strong = Boolean(price && take && price >= take && (firstTakeDone || profitPct >= 3 || dailyPct >= 5 || strongUpsideCandidate(candidate, price)));
        let status = '持仓观察';
        if (price && baseStop && price <= baseStop) status = '触发防守止损';
        else if (price && dynamicStop && price <= dynamicStop && profitPct > 0) status = '触发动态止损观察';
        else if (price && take && price >= take && !firstTakeDone) status = '到达第一止盈';
        else if (strong) status = '强势跟踪';
        return {{
          ...position,
          candidate,
          quote,
          entry,
          price,
          take: take ? Number(take.toFixed(2)) : 0,
          baseStop: baseStop ? Number(baseStop.toFixed(2)) : 0,
          dynamicStop,
          profitPct,
          dailyPct,
          firstTakeDone,
          strong,
          status
        }};
      }});
    }}

    function realtimeAlerts() {{
      const alerts = [];
      paperRiskRows().forEach(row => {{
        const price = numberValue(row.price);
        const take = numberValue(row.take);
        const stop = numberValue(row.baseStop);
        const dynamicStop = numberValue(row.dynamicStop);
        if (!price) return;
        if (stop && price <= stop) {{
          alerts.push({{
            type: 'stop',
            code: row.stock_code,
            name: row.stock_name,
            title: `${{row.stock_code}} ${{row.stock_name}} 触发防守止损`,
            detail: `实时价 ${{price.toFixed(2)}} ≤ 防守止损 ${{stop.toFixed(2)}}。模拟盘持仓优先按纪律处理。`,
          }});
        }} else if (dynamicStop && price <= dynamicStop && numberValue(row.profitPct) > 0) {{
          alerts.push({{
            type: 'stop',
            code: row.stock_code,
            name: row.stock_name,
            title: `${{row.stock_code}} ${{row.stock_name}} 触发动态止损观察`,
            detail: `实时价 ${{price.toFixed(2)}} ≤ 动态止损 ${{dynamicStop.toFixed(2)}}。已有浮盈回落，建议按移动保护位复核。`,
          }});
        }}
        if (take && price >= take && !row.firstTakeDone) {{
          alerts.push({{
            type: 'take',
            code: row.stock_code,
            name: row.stock_name,
            title: `${{row.stock_code}} ${{row.stock_name}} 到达第一止盈`,
            detail: `实时价 ${{price.toFixed(2)}} ≥ 第一止盈 ${{take.toFixed(2)}}。仅针对模拟盘持仓提示，可按纪律先落袋一部分。`,
          }});
        }}
        if (row.strong) {{
          alerts.push({{
            type: 'extra',
            code: row.stock_code,
            name: row.stock_name,
            title: `${{row.stock_code}} ${{row.stock_name}} 强势跟踪标记`,
            detail: `实时价 ${{price.toFixed(2)}}，浮盈 ${{pct(row.profitPct)}}。涨势较强，可保留强势跟踪标记，并参考动态止损 ${{dynamicStop ? dynamicStop.toFixed(2) : '-'}}。`,
          }});
        }}
      }});
      return alerts;
    }}

    function playAlertSound() {{
      if (!liveState.soundEnabled) return;
      try {{
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return;
        const context = new AudioContextClass();
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.type = 'sine';
        oscillator.frequency.value = 880;
        gain.gain.setValueAtTime(0.001, context.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.18, context.currentTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.35);
        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.start();
        oscillator.stop(context.currentTime + 0.36);
      }} catch (error) {{}}
    }}

    function alertHistoryKey() {{
      return `stockAlertHistory:${{data.trade_date || 'unknown'}}`;
    }}

    function readAlertHistory() {{
      try {{
        const rows = JSON.parse(localStorage.getItem(alertHistoryKey()) || '[]');
        return Array.isArray(rows) ? rows : [];
      }} catch (error) {{
        return [];
      }}
    }}

    function writeAlertHistory(rows) {{
      localStorage.setItem(alertHistoryKey(), JSON.stringify(rows.slice(-80)));
    }}

    function recordAlert(alert) {{
      const key = `${{alert.type}}:${{alert.code}}`;
      const rows = readAlertHistory();
      if (rows.some(row => row.key === key)) return;
      rows.push({{
        key,
        type: alert.type,
        code: alert.code,
        name: alert.name,
        title: alert.title,
        detail: alert.detail,
        time: new Date().toLocaleString('zh-CN', {{ hour12: false }})
      }});
      writeAlertHistory(rows);
    }}

    function hydrateAlertedFromHistory() {{
      readAlertHistory().forEach(row => {{
        if (row.key) liveState.alerted.add(row.key);
      }});
    }}

    function openAlertHistory() {{
      const rows = readAlertHistory().slice().reverse();
      const historyRows = rows.length
        ? rows.map(row => `
            <div class="detail-row ${{row.type === 'stop' ? 'weak' : ''}}">
              <div>
                <strong>${{escapeHtml(row.title || `${{row.code}} ${{row.name}}`)}}</strong>
                <span>${{escapeHtml(row.detail || '-')}}</span>
              </div>
              <em>${{escapeHtml(row.time || '-')}}</em>
            </div>
          `).join('')
        : '<div class="paper-note">暂无提醒记录。触发止盈、止损或强势跟踪提示后会自动留痕。</div>';
      openDetailPage('实时提醒记录', `
        <div class="detail-card">
          <h3>今日触发记录</h3>
          <div class="detail-list">${{historyRows}}</div>
        </div>
      `);
    }}

    function renderRiskAlerts() {{
      const box = document.getElementById('riskAlerts');
      const alerts = realtimeAlerts();
      if (!alerts.length) {{
        box.classList.remove('show');
        box.innerHTML = '';
        return;
      }}
      box.classList.add('show');
      box.innerHTML = alerts.map(alert => `
        <div class="risk-alert ${{alert.type === 'extra' ? 'extra' : ''}}">
          <strong>${{escapeHtml(alert.title)}}</strong>
          <span>${{escapeHtml(alert.detail)}}</span>
        </div>
      `).join('');
      alerts.forEach(alert => {{
        const key = `${{alert.type}}:${{alert.code}}`;
        if (liveState.alerted.has(key)) return;
        liveState.alerted.add(key);
        recordAlert(alert);
        playAlertSound();
      }});
    }}

    function renderFocusRealtime() {{
      const rows = paperRiskRows();
      const box = document.getElementById('focusRealtime');
      if (!rows.length) {{
        box.classList.remove('show');
        box.innerHTML = '';
        return;
      }}
      const endpointReady = quoteEndpoints().length > 0;
      const sourceText = liveState.quoteSource ? ` · ${{liveState.quoteSource}}` : '';
      box.classList.add('show');
      const cards = rows.map(row => {{
        const price = numberValue(row.price);
        const take = numberValue(row.take);
        const stop = numberValue(row.baseStop);
        const dynamicStop = numberValue(row.dynamicStop);
        const quote = row.quote || {{}};
        const triggered = row.status.includes('触发') || row.status.includes('到达');
        const tone = price > numberValue(row.entry) ? 'up' : price < numberValue(row.entry) ? 'down' : '';
        const badges = [
          '<span class="position-badge">模拟持仓</span>',
          row.strong ? '<span class="position-badge strong">强势跟踪</span>' : ''
        ].filter(Boolean).join('');
        return `
          <div class="focus-price-card ${{triggered ? 'alert' : ''}} ${{row.strong ? 'strong' : ''}}">
            <div class="position-badges">${{badges}}</div>
            <strong>${{escapeHtml(row.stock_code)}} ${{escapeHtml(row.stock_name)}}</strong>
            <em class="price ${{tone}}">${{price ? price.toFixed(2) : '-'}}</em>
            <span>成本 ${{row.entry ? row.entry.toFixed(2) : '-'}} · 浮盈 ${{pct(row.profitPct)}}</span>
            <span>第一止盈 ${{take ? take.toFixed(2) : '-'}} · 防守止损 ${{stop ? stop.toFixed(2) : '-'}}</span>
            <span>动态止损 ${{dynamicStop ? dynamicStop.toFixed(2) : '-'}} · ${{escapeHtml(row.status)}}</span>
            <span>${{quote.pct_change !== undefined ? `涨跌 ${{pct(quote.pct_change)}} · ` : ''}}${{quote.time ? escapeHtml(quote.time) : '等待实时刷新'}}</span>
          </div>
        `;
      }}).join('');
      box.innerHTML = `
        <div class="focus-realtime-head">
          <h2>模拟持仓实时风控</h2>
          <div class="focus-realtime-meta">
            <button class="sound-toggle ${{liveState.soundEnabled ? 'active' : ''}}" type="button" id="soundToggle">${{liveState.soundEnabled ? '声音已开' : '开启声音'}}</button>
            <button class="sound-toggle" type="button" id="alertHistoryButton">提醒记录</button>
            <span>${{endpointReady ? `每 5 秒刷新 · ${{liveState.lastUpdated || '准备中'}}${{sourceText}}` : '实时刷新待 Worker 更新'}}</span>
          </div>
        </div>
        <div class="focus-price-grid">${{cards}}</div>
      `;
    }}

    function updateCardLivePrices() {{
      document.querySelectorAll('[data-card-live-price]').forEach(item => {{
        const code = item.dataset.cardLivePrice;
        const row = data.candidates.find(candidate => candidate.stock_code === code);
        if (!row) return;
        const price = displayPrice(row);
        item.textContent = price ? price.toFixed(2) : '-';
        item.classList.toggle('down', priceTone(row) === 'down');
      }});
    }}

    function quoteTradeDate() {{
      for (const quote of Object.values(liveState.quotes)) {{
        const text = String(quote.time || '');
        const match = text.match(/\\d{{4}}-\\d{{2}}-\\d{{2}}/);
        if (match) return match[0];
      }}
      const parts = new Intl.DateTimeFormat('zh-CN', {{
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      }}).formatToParts(new Date()).reduce((acc, item) => {{
        acc[item.type] = item.value;
        return acc;
      }}, {{}});
      return `${{parts.year}}-${{parts.month}}-${{parts.day}}`;
    }}

    function sellSharesForHalf(shares) {{
      const half = Math.floor(numberValue(shares) * 0.5 / 100) * 100;
      return half > 0 ? half : numberValue(shares);
    }}

    function appendPaperSell(runtime, position, shares, price, tradeDate, note) {{
      const entryPrice = numberValue(position.entry_price);
      const amount = Number((price * shares).toFixed(2));
      const cost = Number((entryPrice * shares).toFixed(2));
      const pnl = Number((amount - cost).toFixed(2));
      const pnlPct = cost ? Number((pnl / cost * 100).toFixed(2)) : 0;
      runtime.cash = Number((numberValue(runtime.cash) + amount).toFixed(2));
      runtime.realized_pnl = Number((numberValue(runtime.realized_pnl) + pnl).toFixed(2));
      position.remaining_shares = Math.max(0, numberValue(position.remaining_shares) - shares);
      runtime.ledger.push({{
        trade_date: tradeDate,
        action: 'SELL',
        stock_code: position.stock_code,
        stock_name: position.stock_name,
        price: price.toFixed(2),
        shares: String(shares),
        amount: amount.toFixed(2),
        pnl_amount: pnl.toFixed(2),
        pnl_pct: pnlPct.toFixed(2),
        cash_after: numberValue(runtime.cash).toFixed(2),
        note
      }});
    }}

    function updatePaperRuntimeFromQuotes() {{
      const runtime = getPaperRuntime();
      const tradeDate = quoteTradeDate();
      let changed = false;
      runtime.positions.forEach(position => {{
        const remaining = numberValue(position.remaining_shares);
        if (remaining <= 0) {{
          position.live_status = '已卖出';
          return;
        }}
        const quote = liveState.quotes[position.stock_code] || {{}};
        const price = numberValue(quote.price || position.current_price || position.entry_price);
        if (!price) return;
        position.current_price = price;
        position.market_value = Number((price * remaining).toFixed(2));
        position.unrealized_pnl = Number(((price - numberValue(position.entry_price)) * remaining).toFixed(2));
        const cost = numberValue(position.entry_price) * remaining;
        position.unrealized_return_pct = cost ? Number((numberValue(position.unrealized_pnl) / cost * 100).toFixed(2)) : 0;

        if (!position.entry_date || position.entry_date >= tradeDate) {{
          position.live_status = 'T+1 未满足，当日不卖';
          return;
        }}

        const stop = numberValue(position.defensive_stop_point);
        const take = numberValue(position.first_take_profit_point);
        if (stop && price <= stop) {{
          appendPaperSell(runtime, position, remaining, price, tradeDate, `实时模拟：触发防守止损，按实时价 ${{price.toFixed(2)}} 清仓；严格遵守 T+1`);
          position.live_status = '已触发防守止损清仓';
          changed = true;
          return;
        }}
        if (take && price >= take && !position.first_take_done) {{
          const sellShares = sellSharesForHalf(remaining);
          appendPaperSell(runtime, position, sellShares, price, tradeDate, `实时模拟：触发第一止盈，按实时价 ${{price.toFixed(2)}} 卖出 50%；剩余仓位进入强势跟踪`);
          position.first_take_done = true;
          position.live_status = numberValue(position.remaining_shares) > 0 ? '第一止盈已执行，剩余强势跟踪' : '第一止盈已全部卖出';
          changed = true;
          return;
        }}
        if (take && price >= take && position.first_take_done) {{
          position.live_status = '强势跟踪中，跌破分时均价线再处理';
        }} else {{
          position.live_status = '持仓观察中';
        }}
      }});
      runtime.last_live_updated = new Date().toLocaleString('zh-CN', {{ hour12: false }});
      runtime.note = changed ? '实时模拟已根据止盈/止损纪律执行' : '实时价格已同步，未触发新的模拟卖出';
      savePaperRuntime();
    }}

    function paperSnapshot() {{
      const runtime = getPaperRuntime();
      let marketValue = 0;
      let unrealized = 0;
      const positions = runtime.positions
        .filter(row => numberValue(row.remaining_shares) > 0)
        .map(row => {{
          const shares = numberValue(row.remaining_shares);
          const price = numberValue(row.current_price || row.entry_price);
          const value = Number((price * shares).toFixed(2));
          const pnl = Number(((price - numberValue(row.entry_price)) * shares).toFixed(2));
          const cost = numberValue(row.entry_price) * shares;
          marketValue += value;
          unrealized += pnl;
          return {{
            ...row,
            shares,
            current_price: price,
            market_value: value,
            unrealized_pnl: pnl,
            unrealized_return_pct: cost ? Number((pnl / cost * 100).toFixed(2)) : 0
          }};
        }});
      const initial = numberValue(runtime.initial_capital || 1000000);
      const cash = numberValue(runtime.cash);
      const equity = Number((cash + marketValue).toFixed(2));
      const cumulative = Number((equity - initial).toFixed(2));
      return {{
        perf: {{
          initial_capital: initial,
          cash,
          market_value: Number(marketValue.toFixed(2)),
          equity,
          realized_pnl: numberValue(runtime.realized_pnl),
          unrealized_pnl: Number(unrealized.toFixed(2)),
          cumulative_pnl: cumulative,
          cumulative_return_pct: initial ? Number((cumulative / initial * 100).toFixed(2)) : 0,
          last_updated: runtime.last_live_updated || data.generated_at || '',
          note: runtime.note || '实时模拟盘运行中'
        }},
        positions,
        ledger: runtime.ledger || []
      }};
    }}

    async function fetchFocusQuotes() {{
      const endpoints = quoteEndpoints();
      const codesToFetch = quoteCodes();
      if (!endpoints.length || !codesToFetch.length) {{
        renderFocusRealtime();
        renderRiskAlerts();
        updateCardLivePrices();
        renderPaperTrading();
        return;
      }}
      const codes = codesToFetch.join(',');
      let lastError = null;
      for (const baseEndpoint of endpoints) {{
        try {{
          const endpoint = quoteUrl(baseEndpoint);
          const response = await fetch(`${{endpoint}}?codes=${{encodeURIComponent(codes)}}&_=${{Date.now()}}`, {{ method: 'GET', cache: 'no-store' }});
          const result = await response.json();
          if (!response.ok || !result.ok) throw new Error(result.message || '实时行情获取失败');
          liveState.quotes = result.quotes || {{}};
          liveState.lastUpdated = new Date().toLocaleTimeString('zh-CN', {{ hour12: false }});
          liveState.quoteEndpoint = baseEndpoint;
          liveState.quoteSource = quoteSourceLabel(baseEndpoint);
          updatePaperRuntimeFromQuotes();
          lastError = null;
          break;
        }} catch (error) {{
          lastError = error;
        }}
      }}
      if (lastError) {{
        liveState.lastUpdated = '实时刷新失败';
        liveState.quoteSource = '全部行情通道失败';
      }}
      renderFocusRealtime();
      renderRiskAlerts();
      updateCardLivePrices();
      renderPaperTrading();
    }}

    function startRealtimeQuotes() {{
      renderFocusRealtime();
      renderRiskAlerts();
      updateCardLivePrices();
      renderPaperTrading();
      fetchFocusQuotes();
      if (liveState.timer) clearInterval(liveState.timer);
      liveState.timer = setInterval(fetchFocusQuotes, 5000);
    }}

    function renderMetrics() {{
      const sourceDetail = (data.source_counts || []).map(([name, count]) => `${{name}} ${{count}}`).join('，');
      document.getElementById('subtitle').textContent = `生成时间：${{data.generated_at}} · 来源：${{sourceDetail || data.primary_source || '-'}}`;
      const phase = data.recommendation_phase || {{}};
      document.getElementById('marketState').textContent = `市场状态：${{data.market_state}} · ${{phase.label || '-'}}：${{phase.note || '-'}}`;
      document.getElementById('metrics').innerHTML = metricItems.map(item => `
        <div class="metric ${{item.tone || ''}} ${{item.pool ? 'clickable' : ''}} ${{item.pool && state.pool === item.pool ? 'active-filter' : ''}} ${{String(item.value ?? '').length >= 6 ? 'long' : ''}} ${{String(item.value ?? '').length >= 10 ? 'small' : ''}}" ${{item.pool ? `data-metric-pool="${{item.pool}}" role="button" tabindex="0" aria-label="查看${{escapeHtml(item.label)}}列表"` : ''}}>
          ${{item.pool ? `<button class="note-corner" type="button" data-note-pool="${{item.pool}}" aria-label="${{escapeHtml(item.label)}}说明"></button><div class="note-popup">${{escapeHtml(poolNotes[item.pool])}}</div>` : ''}}
          <span>${{escapeHtml(item.label)}}</span>
          <strong>${{escapeHtml(item.value)}}</strong>
        </div>
      `).join('');
    }}

    function percent(part, total) {{
      const base = Number(total || 0);
      if (!base) return '-';
      return `${{(Number(part || 0) / base * 100).toFixed(1)}}%`;
    }}

    function renderFunnel() {{
      const total = data.summary.total_rows || 0;
      const eligible = data.summary.eligible || 0;
      const rawHits = data.summary.raw_candidate_count || 0;
      const finalCount = data.summary.candidate_count || 0;
      const steps = [
        {{ label: '原始采集', value: total, note: `行情接口拿到` }},
        {{ label: '有效主板', value: eligible, note: `剔除 ST、创业板等` }},
        {{ label: '规则命中', value: rawHits, note: `主题/形态/量价命中` }},
        {{ label: '最终展示', value: finalCount, note: `收敛到三类池` }}
      ];
      document.getElementById('screeningFunnel').innerHTML = steps.map((step, index) => {{
        const denominator = index === 0 ? total : steps[index - 1].value;
        return `
          <div class="funnel-step">
            <span>${{escapeHtml(step.label)}}</span>
            <strong>${{escapeHtml(step.value)}}</strong>
            <small>${{escapeHtml(step.note)}} · 保留 ${{escapeHtml(index === 0 ? '100%' : percent(step.value, denominator))}}</small>
          </div>
        `;
      }}).join('');
    }}

    function renderRefreshSummary() {{
      const raw = localStorage.getItem('lastRefreshSummary');
      if (!raw) return;
      localStorage.removeItem('lastRefreshSummary');
      try {{
        const summary = JSON.parse(raw);
        const parts = [
          `来源：${{summary.source || '-'}}`,
          `交易日：${{summary.trade_date || '-'}}`,
          `采集：${{summary.rows || 0}}`,
          `规则命中：${{summary.raw_candidate_count || 0}}`,
          `入池：${{summary.candidate_rows || 0}}`,
          `股票池：${{summary.universe_cache || 0}}`,
          `复盘：${{summary.review_rows || 0}}`
        ];
        if (summary.fallback) parts.push('已启用降级兜底');
        const box = document.getElementById('refreshSummary');
        box.textContent = `刷新完成 · ${{parts.join(' · ')}}`;
        box.classList.add('show');
      }} catch (error) {{
        localStorage.removeItem('lastRefreshSummary');
      }}
    }}

    function renderCoverageNotice() {{
      if (data.summary.coverage_status !== '覆盖偏窄') return;
      const box = document.getElementById('refreshSummary');
      if (box.classList.contains('show')) return;
      box.textContent = `数据覆盖偏窄：当前股票池缓存 ${{data.summary.universe_cache || 0}} 支，建议导入同花顺沪深主板列表后再刷新。`;
      box.classList.add('show');
    }}

    function renderFreshnessNotice() {{
      if (!data.freshness_note || data.freshness_status === '今日数据') return;
      const box = document.getElementById('freshnessBanner');
      box.textContent = `${{data.freshness_status}}：${{data.freshness_note}}`;
      box.classList.add('show');
      if (data.freshness_status === '可能过期' || data.freshness_status === '日期异常' || data.freshness_status === '无数据日期') {{
        box.classList.add('warn');
      }}
    }}

    function renderThemeFilters() {{
      const box = document.getElementById('themeFilters');
      if (!box) return;
      const themes = data.theme_counts.map(([theme]) => theme);
      box.innerHTML = [
        `<button class="theme-chip active" data-theme="ALL">全部</button>`,
        ...themes.map(theme => `<button class="theme-chip" data-theme="${{escapeHtml(theme)}}">${{escapeHtml(theme)}}</button>`)
      ].join('');
      document.querySelectorAll('.theme-chip').forEach(button => {{
        button.addEventListener('click', () => {{
          state.theme = button.dataset.theme;
          document.querySelectorAll('.theme-chip').forEach(item => item.classList.toggle('active', item === button));
          renderCards();
        }});
      }});
    }}

    function renderThemeBars() {{
      const box = document.getElementById('themeBars');
      if (!box) return;
      const max = Math.max(1, ...data.theme_counts.map(([, count]) => count));
      box.innerHTML = data.theme_counts.map(([theme, count]) => `
        <div class="theme-row">
          <span>${{escapeHtml(theme)}}</span>
          <div class="bar"><span style="width:${{Math.round(count / max * 100)}}%"></span></div>
          <strong>${{count}}</strong>
        </div>
      `).join('') || '<div class="empty">暂无主题</div>';
    }}

    function renderWorkflowPanel() {{
      const box = document.getElementById('workflowPanel');
      if (!box) return;
      const workflow = (data.config || {{}}).workflow || {{}};
      const premarket = workflow.premarket_theme_layer || {{}};
      const intraday = workflow.intraday_validation_layer || {{}};
      const tail = workflow.tail_execution_layer || {{}};
      const items = [
        ['1 盘前主题', premarket.pass_rule || premarket.purpose || '先确定主题优先级'],
        ['2 盘中验证', intraday.pass_rule || intraday.purpose || '看板块、量能、分时承接'],
        ['3 尾盘执行', tail.pass_rule || tail.purpose || '只在尾盘窗口按策略执行']
      ];
      box.innerHTML = items.map(([title, text]) => `
        <div class="workflow-step"><strong>${{escapeHtml(title)}}</strong><span>${{escapeHtml(text)}}</span></div>
      `).join('');
    }}

    function renderPaperTrading() {{
      const snapshot = paperSnapshot();
      const perf = snapshot.perf || {{}};
      const positions = snapshot.positions || [];
      const boxes = [document.getElementById('paperTradingHero')].filter(Boolean);
      if (!Object.keys(perf).length) {{
        boxes.forEach(box => {{
          box.innerHTML = '<div class="paper-note">模拟账户尚未生成。下次刷新后会从 100 万初始本金开始记录。</div>';
        }});
        return;
      }}
      const cumulative = numberValue(perf.cumulative_pnl);
      const unrealized = numberValue(perf.unrealized_pnl);
      const metrics = [
        ['当前权益', money(perf.equity)],
        ['累计盈亏', `${{cumulative >= 0 ? '+' : ''}}${{money(cumulative)}}`, cumulative >= 0 ? 'profit' : 'loss'],
        ['浮动盈亏', `${{unrealized >= 0 ? '+' : ''}}${{money(unrealized)}}`, unrealized >= 0 ? 'profit' : 'loss']
      ];
      const html = `
        <div class="paper-metrics">
          ${{metrics.map(([label, value, tone]) => `<div class="paper-metric ${{tone || ''}}"><span>${{escapeHtml(label)}}</span><strong>${{escapeHtml(value)}}</strong></div>`).join('')}}
        </div>
        <div class="paper-note">持仓 ${{positions.length}} 只 · 今日交易 ${{(snapshot.ledger || []).filter(row => row.trade_date === data.trade_date).length}} 笔 · ${{escapeHtml(perf.note || '实时模拟盘运行中')}}</div>
        <div class="paper-actions">
          <button class="paper-detail-button" type="button" data-paper-detail="account">查看模拟交易账本</button>
        </div>
      `;
      boxes.forEach(box => {{
        box.innerHTML = html;
      }});
    }}

    function safeText(value, fallback = '暂无') {{
      const text = String(value || '').trim();
      return text || fallback;
    }}

    function hasMeaningfulRisk(value) {{
      const text = String(value || '').trim();
      return Boolean(text) && !text.includes('暂无明显风险');
    }}

    function openDetailPage(title, html) {{
      document.getElementById('detailTitle').textContent = title;
      document.getElementById('detailContent').innerHTML = html;
      document.getElementById('detailPage').classList.add('show');
      document.getElementById('detailPage').setAttribute('aria-hidden', 'false');
      document.body.classList.add('detail-open');
      window.scrollTo({{ top: 0, behavior: 'auto' }});
    }}

    function closeDetailPage() {{
      document.getElementById('detailPage').classList.remove('show');
      document.getElementById('detailPage').setAttribute('aria-hidden', 'true');
      document.body.classList.remove('detail-open');
    }}

    function detailCard(title, text) {{
      return `<div class="detail-card"><h3>${{escapeHtml(title)}}</h3><p>${{escapeHtml(text)}}</p></div>`;
    }}

    function signedMoney(value) {{
      const n = numberValue(value);
      return `${{n >= 0 ? '+' : ''}}${{money(n)}}`;
    }}

    function pnlTone(value) {{
      const n = numberValue(value);
      if (n > 0) return 'profit';
      if (n < 0) return 'loss';
      return '';
    }}

    function tradeTime(row) {{
      const direct = String(row.trade_time || row.time || '').trim();
      if (direct) return direct;
      const note = String(row.note || '');
      const found = note.match(/(\\d{{1,2}}:\\d{{2}})/);
      if (found) return found[1].padStart(5, '0');
      return row.action === 'BUY' ? '14:57' : '-';
    }}

    function paperPnlAmount(row) {{
      return row.action === 'BUY'
        ? numberValue(row.latest_pnl_amount || row.pnl_amount)
        : numberValue(row.pnl_amount);
    }}

    function paperPnlPct(row) {{
      return row.action === 'BUY'
        ? numberValue(row.latest_pnl_pct || row.pnl_pct)
        : numberValue(row.pnl_pct);
    }}

    function sortedPaperLedger(ledger) {{
      return ledger.slice().sort((a, b) => {{
        const left = `${{a.trade_date || ''}} ${{tradeTime(a)}} ${{a.action || ''}} ${{a.stock_code || ''}}`;
        const right = `${{b.trade_date || ''}} ${{tradeTime(b)}} ${{b.action || ''}} ${{b.stock_code || ''}}`;
        return right.localeCompare(left);
      }});
    }}

    function paperDailyPnl(ledger) {{
      const byDate = new Map();
      ledger.forEach(row => {{
        const date = String(row.trade_date || '').trim();
        if (!date) return;
        const current = byDate.get(date) || {{ pnl: 0, trades: 0 }};
        current.trades += 1;
        if (row.action === 'SELL') current.pnl += numberValue(row.pnl_amount);
        byDate.set(date, current);
      }});
      return byDate;
    }}

    const aShareClosedDates = new Set([
      '2025-01-01',
      '2025-01-28', '2025-01-29', '2025-01-30', '2025-01-31', '2025-02-03', '2025-02-04',
      '2025-04-04',
      '2025-05-01', '2025-05-02', '2025-05-05',
      '2025-06-02',
      '2025-10-01', '2025-10-02', '2025-10-03', '2025-10-06', '2025-10-07', '2025-10-08',
      '2026-01-01', '2026-01-02',
      '2026-02-16', '2026-02-17', '2026-02-18', '2026-02-19', '2026-02-20', '2026-02-23',
      '2026-04-06',
      '2026-05-01', '2026-05-04', '2026-05-05',
      '2026-06-19',
      '2026-09-25',
      '2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06', '2026-10-07'
    ]);

    function localIsoDate(now = new Date()) {{
      const year = now.getFullYear();
      const month = String(now.getMonth() + 1).padStart(2, '0');
      const day = String(now.getDate()).padStart(2, '0');
      return `${{year}}-${{month}}-${{day}}`;
    }}

    function defaultPaperMonth(ledger) {{
      const daily = paperDailyPnl(ledger);
      const dates = Array.from(daily.keys()).sort();
      return (data.trade_date || dates[dates.length - 1] || localIsoDate()).slice(0, 7);
    }}

    function isAShareClosed(date) {{
      const parsed = new Date(`${{date}}T00:00:00`);
      const day = parsed.getDay();
      return day === 0 || day === 6 || aShareClosedDates.has(date);
    }}

    function paperMonthlyCalendar(ledger, month = defaultPaperMonth(ledger)) {{
      const daily = paperDailyPnl(ledger);
      const first = new Date(`${{month}}-01T00:00:00`);
      const daysInMonth = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
      const offset = (first.getDay() + 6) % 7;
      const today = localIsoDate();
      const headers = ['一', '二', '三', '四', '五', '六', '日'].map(day => `<div class="calendar-head">${{day}}</div>`).join('');
      const blanks = Array.from({{ length: offset }}, () => '<div class="calendar-day empty"></div>').join('');
      const days = Array.from({{ length: daysInMonth }}, (_, index) => {{
        const day = index + 1;
        const date = `${{month}}-${{String(day).padStart(2, '0')}}`;
        const item = daily.get(date) || {{ pnl: 0, trades: 0 }};
        const closed = isAShareClosed(date);
        const tone = item.pnl > 0 ? 'profit' : item.pnl < 0 ? 'loss' : '';
        const todayClass = date === today ? 'today' : '';
        const closedClass = closed ? 'closed' : '';
        let amount = '';
        if (item.trades) {{
          const note = closed ? `休市 · ${{item.trades}} 笔交易` : `${{item.trades}} 笔交易`;
          amount = `<span class="${{pnlTone(item.pnl)}}-text">${{signedMoney(item.pnl)}}</span><em>${{note}}</em>`;
        }} else {{
          amount = `<em>${{closed ? '休市' : '无交易'}}</em>`;
        }}
        return `<button class="calendar-day ${{tone}} ${{todayClass}} ${{closedClass}}" type="button" data-calendar-date="${{date}}"><strong>${{day}}</strong>${{amount}}</button>`;
      }}).join('');
      return `<div class="calendar-grid">${{headers}}${{blanks}}${{days}}</div>`;
    }}

    function paperStockSummary(ledger) {{
      const map = new Map();
      ledger.forEach(row => {{
        const key = `${{row.stock_code || '-'}} ${{row.stock_name || ''}}`;
        const item = map.get(key) || {{ code: row.stock_code || '-', name: row.stock_name || '', buys: 0, sells: 0, amount: 0, pnl: 0 }};
        if (row.action === 'BUY') item.buys += 1;
        if (row.action === 'SELL') {{
          item.sells += 1;
          item.pnl += numberValue(row.pnl_amount);
        }}
        item.amount += numberValue(row.amount);
        map.set(key, item);
      }});
      const rows = Array.from(map.values()).sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl));
      if (!rows.length) return '<div class="paper-note">暂无股票汇总。</div>';
      return `
        <div class="paper-table-wrap">
          <table class="paper-table">
            <thead><tr><th>股票</th><th>买入</th><th>卖出</th><th>累计成交</th><th>已实现盈亏</th></tr></thead>
            <tbody>
              ${{rows.map(row => `
                <tr>
                  <td><strong>${{escapeHtml(row.code)}} ${{escapeHtml(row.name)}}</strong></td>
                  <td>${{row.buys}}</td>
                  <td>${{row.sells}}</td>
                  <td>${{money(row.amount)}}</td>
                  <td class="${{pnlTone(row.pnl)}}-text">${{signedMoney(row.pnl)}}</td>
                </tr>
              `).join('')}}
            </tbody>
          </table>
        </div>
      `;
    }}

    function bindPaperLedgerControls() {{
      const tableBody = document.getElementById('paperLedgerRows');
      if (!tableBody) return;
      const ledger = sortedPaperLedger(paperSnapshot().ledger || []);
      const controls = {{
        from: document.getElementById('paperFilterFrom'),
        to: document.getElementById('paperFilterTo'),
        stock: document.getElementById('paperFilterStock'),
        action: document.getElementById('paperFilterAction'),
        result: document.getElementById('paperFilterResult'),
        sort: document.getElementById('paperSort'),
        calendarMonth: document.getElementById('paperCalendarMonth')
      }};
      const calendarBody = document.getElementById('paperCalendarBody');
      const renderCalendar = () => {{
        if (!calendarBody || !controls.calendarMonth) return;
        calendarBody.innerHTML = paperMonthlyCalendar(ledger, controls.calendarMonth.value || defaultPaperMonth(ledger));
        bindCalendarButtons();
      }};
      const render = () => {{
        const query = String(controls.stock.value || '').trim().toLowerCase();
        let rows = ledger.filter(row => {{
          const date = String(row.trade_date || '');
          if (controls.from.value && date < controls.from.value) return false;
          if (controls.to.value && date > controls.to.value) return false;
          if (controls.action.value !== 'ALL' && row.action !== controls.action.value) return false;
          if (query && !`${{row.stock_code || ''}} ${{row.stock_name || ''}}`.toLowerCase().includes(query)) return false;
          const pnl = paperPnlAmount(row);
          if (controls.result.value === 'PROFIT' && pnl <= 0) return false;
          if (controls.result.value === 'LOSS' && pnl >= 0) return false;
          return true;
        }});
        rows.sort((a, b) => {{
          if (controls.sort.value === 'pnl_desc') return paperPnlAmount(b) - paperPnlAmount(a);
          if (controls.sort.value === 'pnl_asc') return paperPnlAmount(a) - paperPnlAmount(b);
          if (controls.sort.value === 'pct_desc') return paperPnlPct(b) - paperPnlPct(a);
          if (controls.sort.value === 'pct_asc') return paperPnlPct(a) - paperPnlPct(b);
          if (controls.sort.value === 'amount_desc') return numberValue(b.amount) - numberValue(a.amount);
          return `${{b.trade_date || ''}} ${{tradeTime(b)}}`.localeCompare(`${{a.trade_date || ''}} ${{tradeTime(a)}}`);
        }});
        tableBody.innerHTML = rows.length ? rows.map(row => {{
          const pnl = paperPnlAmount(row);
          const actionLabel = row.action === 'SELL' ? '卖出' : '买入';
          const actionClass = row.action === 'SELL' ? 'sell' : 'buy';
          return `
            <tr>
              <td>${{escapeHtml(row.trade_date || '-')}}</td>
              <td>${{escapeHtml(tradeTime(row))}}</td>
              <td><span class="action-badge ${{actionClass}}">${{actionLabel}}</span></td>
              <td><strong>${{escapeHtml(row.stock_code || '-')}} ${{escapeHtml(row.stock_name || '')}}</strong></td>
              <td>${{escapeHtml(row.price || '-')}}</td>
              <td>${{escapeHtml(row.shares || '-')}}</td>
              <td>${{money(row.amount)}}</td>
              <td class="${{pnlTone(pnl)}}-text">${{signedMoney(pnl)}}</td>
              <td class="${{pnlTone(pnl)}}-text">${{pct(paperPnlPct(row))}}</td>
              <td class="note-cell">${{escapeHtml(row.note || '-')}}</td>
            </tr>
          `;
        }}).join('') : '<tr><td colspan="10">没有符合条件的交易记录。</td></tr>';
      }};
      Object.entries(controls).forEach(([key, control]) => {{
        if (!control || key === 'calendarMonth') return;
        control.addEventListener('input', render);
        control.addEventListener('change', render);
      }});
      if (controls.calendarMonth) {{
        controls.calendarMonth.addEventListener('change', renderCalendar);
        controls.calendarMonth.addEventListener('input', renderCalendar);
      }}
      function bindCalendarButtons() {{
        document.querySelectorAll('[data-calendar-date]').forEach(button => {{
          button.addEventListener('click', () => {{
            const date = button.dataset.calendarDate;
            controls.from.value = date;
            controls.to.value = date;
            render();
            document.getElementById('paperLedgerTableCard')?.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
          }});
        }});
      }}
      renderCalendar();
      render();
    }}

    function openCandidateDetail(index, section) {{
      const row = data.candidates[Number(index)];
      if (!row) return;
      const stock = `${{row.stock_code}} ${{row.stock_name}}`;
      if (section === 'score') {{
        openDetailPage(`${{stock}} · 排序依据`, detailCard('排序依据', safeText(row.score_reasons)));
        return;
      }}
      if (section === 'reason') {{
        openDetailPage(`${{stock}} · 入选原因`, detailCard('入选原因', safeText(row.entry_reasons)));
        return;
      }}
      if (section === 'risk') {{
        openDetailPage(`${{stock}} · 风险标签`, detailCard('风险标签', safeText(row.risk_tags)));
        return;
      }}
      if (section === 'sell') {{
        openDetailPage(`${{stock}} · 次日卖出纪律`, `
          ${{detailCard('止盈', safeText(row.next_day_valid_if || '待补充'))}}
          ${{detailCard('时间止损', safeText(row.next_day_weak_if || '待补充'))}}
          ${{detailCard('失效退出', safeText(row.next_day_remove_if || '待补充'))}}
        `);
      }}
    }}

    function openPaperDetail() {{
      const snapshot = paperSnapshot();
      const perf = snapshot.perf || {{}};
      const positions = snapshot.positions || [];
      const ledger = snapshot.ledger || [];
      const realized = ledger.filter(row => row.action === 'SELL').reduce((sum, row) => sum + numberValue(row.pnl_amount), 0);
      const sellRows = ledger.filter(row => row.action === 'SELL');
      const wins = sellRows.filter(row => numberValue(row.pnl_amount) > 0).length;
      const winRate = sellRows.length ? wins / sellRows.length * 100 : 0;
      const biggestWin = sellRows.reduce((max, row) => Math.max(max, numberValue(row.pnl_amount)), 0);
      const biggestLoss = sellRows.reduce((min, row) => Math.min(min, numberValue(row.pnl_amount)), 0);
      const dates = Array.from(new Set(ledger.map(row => row.trade_date).filter(Boolean))).sort();
      const earliest = dates[0] || '';
      const latest = dates[dates.length - 1] || '';
      const positionRows = positions.length
        ? positions.map(row => {{
            const pnl = numberValue(row.unrealized_pnl);
            return `
              <div class="detail-row ${{pnl < 0 ? 'weak' : ''}}">
                <div>
                  <strong>${{escapeHtml(row.stock_code)}} ${{escapeHtml(row.stock_name)}}</strong>
                  <span>${{escapeHtml(row.shares)}} 股 · 买入 ${{escapeHtml(row.entry_price)}} · 最新 ${{money(row.current_price)}} · 市值 ${{money(row.market_value)}} · ${{escapeHtml(row.live_status || '持仓观察中')}}</span>
                </div>
                <em>${{pnl >= 0 ? '+' : ''}}${{money(pnl)}} / ${{pct(row.unrealized_return_pct)}}</em>
              </div>
            `;
          }}).join('')
        : '<div class="paper-note">当前空仓。未到尾盘窗口或当天没有重点关注时不会建仓。</div>';
      openDetailPage('模拟交易账本', `
        <div class="paper-ledger-grid">
          <div class="detail-card">
            <h3>账户总览</h3>
            <div class="paper-summary-grid">
              <div class="paper-summary-item"><span>当前权益</span><strong>${{money(perf.equity)}}</strong></div>
              <div class="paper-summary-item"><span>现金 / 持仓市值</span><strong>${{money(perf.cash)}} / ${{money(perf.market_value)}}</strong></div>
              <div class="paper-summary-item ${{pnlTone(perf.cumulative_pnl)}}"><span>累计盈亏</span><strong>${{signedMoney(perf.cumulative_pnl)}} / ${{pct(perf.cumulative_return_pct)}}</strong></div>
              <div class="paper-summary-item ${{pnlTone(perf.unrealized_pnl)}}"><span>浮动盈亏</span><strong>${{signedMoney(perf.unrealized_pnl)}}</strong></div>
              <div class="paper-summary-item ${{pnlTone(realized)}}"><span>已实现盈亏</span><strong>${{signedMoney(realized)}}</strong></div>
              <div class="paper-summary-item"><span>交易笔数</span><strong>${{ledger.length}} 笔</strong></div>
              <div class="paper-summary-item"><span>卖出胜率</span><strong>${{pct(winRate)}}</strong></div>
              <div class="paper-summary-item"><span>最大单笔盈亏</span><strong><span class="profit-text">${{signedMoney(biggestWin)}}</span> / <span class="loss-text">${{signedMoney(biggestLoss)}}</span></strong></div>
            </div>
            <p>更新时间：${{escapeHtml(perf.last_updated || data.generated_at || '-')}}</p>
          </div>
          <div class="detail-card">
            <h3>月度盈亏日历</h3>
            <div class="calendar-toolbar">
              <label>选择年月<input id="paperCalendarMonth" type="month" value="${{escapeHtml(defaultPaperMonth(ledger))}}"></label>
              <span class="calendar-legend">灰色为 A 股休市日，日期保留。</span>
            </div>
            <div id="paperCalendarBody">${{paperMonthlyCalendar(ledger)}}</div>
          </div>
          <div class="detail-card" id="paperLedgerTableCard">
            <h3>交易记录</h3>
            <div class="paper-filter-bar">
              <label>开始日期<input id="paperFilterFrom" type="date" value="${{escapeHtml(earliest)}}"></label>
              <label>结束日期<input id="paperFilterTo" type="date" value="${{escapeHtml(latest)}}"></label>
              <label>股票筛选<input id="paperFilterStock" placeholder="代码或名称"></label>
              <label>买卖方向<select id="paperFilterAction"><option value="ALL">全部</option><option value="BUY">买入</option><option value="SELL">卖出</option></select></label>
              <label>盈亏筛选<select id="paperFilterResult"><option value="ALL">全部</option><option value="PROFIT">盈利</option><option value="LOSS">亏损</option></select></label>
              <label>排序<select id="paperSort"><option value="time_desc">时间最新</option><option value="pnl_desc">利润值高到低</option><option value="pnl_asc">利润值低到高</option><option value="pct_desc">利润率高到低</option><option value="pct_asc">利润率低到高</option><option value="amount_desc">成交额高到低</option></select></label>
            </div>
            <div class="paper-table-wrap" style="margin-top:10px">
              <table class="paper-table">
                <thead>
                  <tr><th>日期</th><th>时间</th><th>方向</th><th>股票</th><th>价格</th><th>数量</th><th>成交额</th><th>利润值</th><th>利润率</th><th>说明</th></tr>
                </thead>
                <tbody id="paperLedgerRows"></tbody>
              </table>
            </div>
          </div>
          <div class="detail-card"><h3>当前持仓</h3><div class="detail-list">${{positionRows}}</div></div>
          <div class="detail-card"><h3>按股票汇总</h3>${{paperStockSummary(ledger)}}</div>
        </div>
      `);
      bindPaperLedgerControls();
    }}

    function renderRuleConfig() {{
      const box = document.getElementById('ruleConfig');
      if (!box) return;
      const config = data.config || {{}};
      const caps = config.pool_caps || {{}};
      const themes = config.theme_names || [];
      const warnings = config.warnings || [];
      box.innerHTML = `
        <div class="config-line"><span>配置状态</span><strong>${{escapeHtml(config.status || '-')}}</strong></div>
        <div class="config-line"><span>入池上限</span><strong>A${{escapeHtml(caps.A ?? '-')}} / B${{escapeHtml(caps.B ?? '-')}} / C${{escapeHtml(caps.C ?? '-')}}</strong></div>
        <div class="config-line"><span>规则文件</span><strong>${{escapeHtml(config.rules_path || '-')}}</strong></div>
        <div class="config-tags">${{themes.length ? themes.map(theme => `<span class="tag">${{escapeHtml(theme)}}</span>`).join('') : '<span class="tag">无</span>'}}</div>
        ${{warnings.length ? `<div class="config-warning">${{warnings.map(escapeHtml).join('<br>')}}</div>` : ''}}
      `;
    }}

    function tagsHtml(value, className = 'tag') {{
      const tags = splitTags(value);
      return tags.length ? tags.map(tag => `<span class="${{className}}">${{escapeHtml(tag)}}</span>`).join('') : '<span class="tag">无</span>';
    }}

    function matches(row) {{
      const text = [row.stock_code, row.stock_name, row.theme_tags, row.matched_strategies, row.entry_reasons].join(' ').toLowerCase();
      const themes = splitTags(row.theme_tags);
      const queryOk = !state.query || text.includes(state.query.toLowerCase());
      const poolOk = state.pool === 'ALL' || row.pool_level === state.pool;
      const themeOk = state.theme === 'ALL' || themes.includes(state.theme);
      return queryOk && poolOk && themeOk;
    }}

    function setPoolFilter(pool, shouldScroll = true) {{
      state.pool = state.pool === pool ? 'ALL' : pool;
      renderMetrics();
      renderCards();
      if (shouldScroll) {{
        document.querySelector('.board')?.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }}
    }}

    function renderCards() {{
      const rows = data.candidates.filter(matches);
      document.getElementById('resultCount').textContent = `当前显示 ${{rows.length}} 只，全部候选 ${{data.candidates.length}} 只`;
      if (!rows.length) {{
        const message = data.candidates.length
          ? '当前筛选条件下暂无候选'
          : '底层防御已开启：行情或信号不足，没有合适股票可以不推，当前以空仓等待为主';
        document.getElementById('cards').innerHTML = `<div class="empty">${{escapeHtml(message)}}</div>`;
        return;
      }}
      document.getElementById('cards').innerHTML = rows.map(row => {{
        const risks = row.risk_tags || '';
        const showRisk = hasMeaningfulRisk(risks);
        return `
          <article class="candidate">
            <div class="candidate-head">
              <div class="pool ${{escapeHtml(row.pool_level)}}">${{escapeHtml(poolLabel[row.pool_level] || row.pool_level)}}</div>
              <div>
                <div class="name">${{escapeHtml(row.stock_name)}}</div>
                <div class="code">${{escapeHtml(row.stock_code)}} · ${{escapeHtml(row.universe)}}</div>
              </div>
              <div class="change">${{escapeHtml(row.pct_change)}}%</div>
            </div>
            <div class="candidate-body">
              ${{row.pool_level === 'A' ? `
                <div class="live-price-line">
                  <span>实时价 · 5秒刷新</span>
                  <strong data-card-live-price="${{escapeHtml(row.stock_code)}}">${{displayPrice(row) ? displayPrice(row).toFixed(2) : '-'}}</strong>
                </div>
              ` : ''}}
              <div class="tags">${{tagsHtml(row.theme_tags)}}${{tagsHtml(row.matched_strategies, 'tag strategy')}}</div>
              <div class="scoreline">
                <span class="score-pill" title="基础分 ${{escapeHtml(row.base_candidate_score || row.candidate_score || '-')}}，消息辅助最高 +10">评分 ${{escapeHtml(row.candidate_score || '-')}}</span>
                <span class="score-pill" title="${{escapeHtml(row.theme_signal_detail || '暂无消息辅助信号')}}">消息 +${{escapeHtml(row.theme_signal_score || '0')}}/10</span>
                <span class="score-pill">池内排名 #${{escapeHtml(row.pool_rank || '-')}}</span>
                <span class="score-pill">原始池 ${{escapeHtml(poolLabel[row.pool_raw_level] || row.pool_raw_level || '-')}}</span>
              </div>
              ${{row.pool_level === 'A' && row.buy_point ? `
                <div class="point-grid" title="${{escapeHtml(row.point_basis || '')}}">
                  <div class="point"><span>买入点</span><strong>${{escapeHtml(row.buy_point)}}</strong></div>
                  <div class="point"><span>第一止盈</span><strong>${{escapeHtml(row.first_take_profit_point || row.sell_point || '-')}}</strong></div>
                  <div class="point follow"><span>强势跟踪</span><strong>${{escapeHtml(row.strong_follow_rule || '跌破分时均价线卖出')}}</strong></div>
                  <div class="point stop"><span>防守止损</span><strong>${{escapeHtml(row.defensive_stop_point || row.stop_point || '-')}}</strong></div>
                </div>
              ` : ''}}
              <div class="stats">
                <div class="stat"><span>量比</span><strong>${{escapeHtml(row.volume_ratio)}}</strong></div>
                <div class="stat"><span>换手</span><strong>${{escapeHtml(row.turnover_rate)}}%</strong></div>
                <div class="stat"><span>收盘位置</span><strong>${{escapeHtml(row.close_position_pct)}}%</strong></div>
              </div>
              <div class="detail-actions">
                ${{row.score_reasons ? `<button class="detail-button" type="button" data-candidate-detail="${{row.__idx}}" data-section="score">排序依据</button>` : ''}}
                ${{row.entry_reasons ? `<button class="detail-button" type="button" data-candidate-detail="${{row.__idx}}" data-section="reason">入选原因</button>` : ''}}
                ${{showRisk ? `<button class="detail-button" type="button" data-candidate-detail="${{row.__idx}}" data-section="risk">风险标签</button>` : ''}}
                <button class="detail-button" type="button" data-candidate-detail="${{row.__idx}}" data-section="sell">次日卖出纪律</button>
              </div>
            </div>
          </article>
        `;
      }}).join('');
    }}

    function renderExcluded() {{
      if (!data.excluded.length) {{
        document.getElementById('excluded').innerHTML = '';
        return;
      }}
      document.getElementById('excluded').innerHTML = `
        <details>
          <summary>已剔除股票 ${{data.excluded.length}} 只</summary>
          <ul>${{data.excluded.map(row => `<li>${{escapeHtml(row.stock_code)}} ${{escapeHtml(row.stock_name)}}：${{escapeHtml(row.exclude_reason)}}</li>`).join('')}}</ul>
        </details>
      `;
    }}

    function bindControls() {{
      document.getElementById('search').addEventListener('input', event => {{
        state.query = event.target.value;
        renderCards();
      }});
      document.getElementById('refreshData').addEventListener('click', refreshData);
      document.getElementById('detailBack').addEventListener('click', closeDetailPage);
      document.getElementById('focusRealtime').addEventListener('click', event => {{
        const soundButton = event.target.closest('#soundToggle');
        if (soundButton) {{
          liveState.soundEnabled = !liveState.soundEnabled;
          renderFocusRealtime();
          return;
        }}
        const historyButton = event.target.closest('#alertHistoryButton');
        if (historyButton) {{
          openAlertHistory();
        }}
      }});
      document.getElementById('detailPage').addEventListener('click', event => {{
        if (event.target.id === 'detailPage') closeDetailPage();
      }});
      document.addEventListener('keydown', event => {{
        if (event.key === 'Escape') closeDetailPage();
      }});
      document.getElementById('paperTradingHero').addEventListener('click', event => {{
        const button = event.target.closest('[data-paper-detail]');
        if (!button) return;
        openPaperDetail();
      }});
      document.getElementById('cards').addEventListener('click', event => {{
        const button = event.target.closest('[data-candidate-detail]');
        if (!button) return;
        openCandidateDetail(button.dataset.candidateDetail, button.dataset.section);
      }});
      document.getElementById('metrics').addEventListener('click', event => {{
        const noteButton = event.target.closest('.note-corner');
        if (noteButton) {{
          event.stopPropagation();
          const metric = noteButton.closest('.metric');
          document.querySelectorAll('.metric.show-note').forEach(item => {{
            if (item !== metric) item.classList.remove('show-note');
          }});
          metric.classList.toggle('show-note');
          return;
        }}
        const metric = event.target.closest('[data-metric-pool]');
        if (!metric) return;
        setPoolFilter(metric.dataset.metricPool);
      }});
      document.getElementById('metrics').addEventListener('keydown', event => {{
        if (event.key !== 'Enter' && event.key !== ' ') return;
        const metric = event.target.closest('[data-metric-pool]');
        if (!metric) return;
        event.preventDefault();
        setPoolFilter(metric.dataset.metricPool);
      }});
      document.addEventListener('click', () => {{
        document.querySelectorAll('.metric.show-note').forEach(item => item.classList.remove('show-note'));
      }});
    }}

    async function refreshData() {{
      const button = document.getElementById('refreshData');
      const label = document.getElementById('refreshState');
      button.disabled = true;
      label.textContent = '刷新中...';
      try {{
        const isGithubPages = location.hostname.endsWith('github.io');
        const cloudEndpoint = data.cloud_refresh_endpoint || '';
        if (isGithubPages) {{
          if (!cloudEndpoint) {{
            label.textContent = '云端刷新待配置';
            alert('固定链接上的刷新需要先配置云端触发接口。自动定时刷新已由 GitHub Actions 接管；按钮直刷需要部署 Cloudflare Worker 后填写接口地址。');
            button.disabled = false;
            return;
          }}
          const cloudResponse = await fetch(cloudEndpoint, {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ source: 'github-pages-button' }})
          }});
          const cloudResult = await cloudResponse.json();
          if (!cloudResponse.ok || !cloudResult.ok) {{
            throw new Error(cloudResult.message || '云端刷新启动失败');
          }}
          label.textContent = '云端刷新已启动';
          alert(cloudResult.message || '云端刷新已启动，通常 1-3 分钟后刷新页面查看。');
          button.disabled = false;
          return;
        }}
        const response = await fetch('/api/refresh', {{ method: 'POST' }});
        const result = await response.json();
        if (!response.ok || !result.ok) {{
          throw new Error(result.message || '刷新失败');
        }}
        label.textContent = '刷新完成';
        localStorage.setItem('lastRefreshSummary', JSON.stringify(result.summary || {{}}));
        window.location.href = `/?v=${{Date.now()}}`;
      }} catch (error) {{
        label.textContent = error.message || '刷新失败';
        button.disabled = false;
      }}
    }}

    renderRefreshSummary();
    renderCoverageNotice();
    renderFreshnessNotice();
    renderMetrics();
    renderFunnel();
    // Theme filters, workflow notes, and rule config are intentionally hidden.
    renderPaperTrading();
    bindControls();
    renderCards();
    renderExcluded();
    hydrateAlertedFromHistory();
    startRealtimeQuotes();
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local A-share dashboard.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Candidate CSV path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Dashboard HTML path")
    args = parser.parse_args()

    rows = read_csv(args.input)
    data = to_dashboard_data(rows, args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(data), encoding="utf-8")
    print(f"Built dashboard: {args.output}")


if __name__ == "__main__":
    main()
