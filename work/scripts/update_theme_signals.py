#!/usr/bin/env python3
"""Build lightweight theme signal scores for candidate screening.

The output is intentionally small and explainable. Scores are capped at 10 by
screen_candidates.py and are used only as an auxiliary ranking signal.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATES = ROOT / "work" / "normalized_data" / "candidates_latest.csv"
DEFAULT_OUTPUT = ROOT / "work" / "theme_signals" / "theme_signals_latest.csv"
DEFAULT_MANUAL = ROOT / "work" / "theme_signals" / "manual_theme_signals.csv"

FIELDS = [
    "signal_date",
    "theme",
    "source_type",
    "source_name",
    "title",
    "keywords",
    "score",
    "reliability_score",
    "relevance_score",
    "market_confirm_score",
    "freshness_score",
    "risk_penalty",
    "direction",
    "raw_value",
    "note",
    "captured_at",
]

OVERSEAS_THEME_MAP = {
    "半导体": [
        ("^SOX", "费城半导体指数"),
        ("SMH", "VanEck 半导体ETF"),
        ("NVDA", "英伟达"),
        ("AMD", "AMD"),
        ("AVGO", "博通"),
        ("TSM", "台积电ADR"),
    ],
    "科技": [
        ("^IXIC", "纳斯达克综合指数"),
        ("QQQ", "纳指100ETF"),
        ("NVDA", "英伟达"),
        ("MSFT", "微软"),
        ("GOOGL", "谷歌"),
        ("META", "Meta"),
    ],
    "PCB": [
        ("SMH", "半导体ETF"),
        ("AVGO", "博通"),
        ("NVDA", "英伟达"),
    ],
    "电力": [
        ("XLU", "美国公用事业ETF"),
        ("ICLN", "全球清洁能源ETF"),
    ],
    "商业航天": [
        ("ITA", "美国航空航天与国防ETF"),
        ("ARKX", "ARK太空探索ETF"),
        ("LMT", "洛克希德马丁"),
    ],
}

THEME_KEYWORDS = {
    "半导体": "半导体;芯片;封测;先进封装;设备;存储;算力",
    "科技": "AI;算力;数据中心;云计算;服务器;通信;消费电子",
    "PCB": "PCB;覆铜板;高速板;HDI;载板;AI服务器",
    "电力": "电力;绿电;储能;电网;特高压;清洁能源",
    "商业航天": "商业航天;卫星;航天;低轨卫星;军工电子",
}


def num(value: object, default: float = 0.0) -> float:
    try:
        raw = str(value or "").replace(",", "").strip()
        return float(raw) if raw else default
    except ValueError:
        return default


def yes(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "是"}


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as file:
        return [dict(row) for row in csv.DictReader(file)]


def yahoo_pct_change(symbol: str, timeout: int = 8) -> Tuple[float, str]:
    encoded = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=5d&interval=1d"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("chart", {}).get("result", [])
    if not result:
        raise ValueError("empty yahoo result")
    closes = [item for item in result[0].get("indicators", {}).get("quote", [{}])[0].get("close", []) if item]
    timestamps = result[0].get("timestamp", [])
    if len(closes) < 2:
        raise ValueError("not enough closes")
    pct = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] else 0.0
    signal_date = datetime.now().strftime("%Y-%m-%d")
    if timestamps:
        signal_date = datetime.fromtimestamp(timestamps[-1]).strftime("%Y-%m-%d")
    return round(pct, 2), signal_date


def overseas_score(moves: List[Tuple[str, str, float]]) -> float:
    positives = [pct for _, _, pct in moves if pct >= 1.0]
    if not positives:
        return 0.0
    avg_pct = statistics.mean(positives)
    breadth = len(positives)
    return round(min(6.0, 2.0 + min(avg_pct, 4.0) * 0.65 + min(breadth, 4) * 0.35), 2)


def collect_overseas_signals() -> List[Dict[str, str]]:
    captured_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    signals: List[Dict[str, str]] = []
    for theme, symbols in OVERSEAS_THEME_MAP.items():
        moves: List[Tuple[str, str, float]] = []
        signal_date = ""
        for symbol, name in symbols:
            try:
                pct, day = yahoo_pct_change(symbol)
                signal_date = max(signal_date, day) if signal_date else day
                moves.append((symbol, name, pct))
            except Exception:
                continue
        signal_date = signal_date or datetime.now().strftime("%Y-%m-%d")
        score = overseas_score(moves)
        if score <= 0:
            continue
        leaders = sorted([item for item in moves if item[2] >= 1.0], key=lambda item: item[2], reverse=True)[:3]
        leader_text = "、".join(f"{name}{pct:+.2f}%" for _, name, pct in leaders)
        signals.append({
            "signal_date": signal_date,
            "theme": theme,
            "source_type": "overseas_market",
            "source_name": "Yahoo Finance 海外行情映射",
            "title": f"隔夜海外映射偏强：{leader_text}",
            "keywords": THEME_KEYWORDS.get(theme, ""),
            "score": f"{score:.2f}",
            "reliability_score": "2.4",
            "relevance_score": "1.6",
            "market_confirm_score": "",
            "freshness_score": "1.0",
            "risk_penalty": "0",
            "direction": "positive",
            "raw_value": ";".join(f"{symbol}:{pct:+.2f}%" for symbol, _, pct in moves),
            "note": "海外映射只做辅助排序，不直接构成A池买点",
            "captured_at": captured_at,
        })
    return signals


def collect_domestic_confirmation(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    captured_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    by_theme: Dict[str, Dict[str, float]] = {}
    trade_date = datetime.now().strftime("%Y-%m-%d")
    for row in rows:
        trade_date = row.get("trade_date") or trade_date
        themes = [item.strip() for item in str(row.get("theme_tags") or "").replace("；", ";").split(";") if item.strip()]
        for theme in themes:
            stat = by_theme.setdefault(theme, {"limit_up": 0.0, "rank": 99.0, "reflow": 0.0, "count": 0.0})
            stat["limit_up"] = max(stat["limit_up"], num(row.get("real_theme_limit_up_count") or row.get("theme_limit_up_count")))
            rank = num(row.get("theme_rank"), 99.0)
            stat["rank"] = min(stat["rank"], rank if rank else 99.0)
            stat["reflow"] += 1.0 if yes(row.get("theme_tail_reflow")) else 0.0
            stat["count"] += 1.0

    signals: List[Dict[str, str]] = []
    for theme, stat in by_theme.items():
        score = 0.0
        if stat["limit_up"] >= 3:
            score += 1.4
        if stat["rank"] <= 3:
            score += 0.9
        if stat["reflow"] >= 2:
            score += 0.7
        score = round(min(3.0, score), 2)
        if score <= 0:
            continue
        signals.append({
            "signal_date": trade_date,
            "theme": theme,
            "source_type": "market",
            "source_name": "A股板块承接",
            "title": f"A股板块承接：涨停扩散{stat['limit_up']:.0f}，主题排名{stat['rank']:.0f}",
            "keywords": THEME_KEYWORDS.get(theme, ""),
            "score": f"{score:.2f}",
            "reliability_score": "2.2",
            "relevance_score": "",
            "market_confirm_score": f"{score:.2f}",
            "freshness_score": "1.0",
            "risk_penalty": "0",
            "direction": "positive",
            "raw_value": f"limit_up={stat['limit_up']:.0f};rank={stat['rank']:.0f};reflow={stat['reflow']:.0f}",
            "note": "仅验证主题有资金承接，不能替代个股量价规则",
            "captured_at": captured_at,
        })
    return signals


def normalize_manual_signals(path: Path) -> List[Dict[str, str]]:
    rows = read_csv(path)
    captured_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized: List[Dict[str, str]] = []
    for row in rows:
        item = {field: row.get(field, "") for field in FIELDS}
        item["captured_at"] = item["captured_at"] or captured_at
        item["source_type"] = item["source_type"] or "official"
        item["source_name"] = item["source_name"] or "手工高可信消息"
        item["score"] = item["score"] or item.get("theme_signal_score", "") or "0"
        normalized.append(item)
    return normalized


def write_signals(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect lightweight theme/news signals for A股短线助手.")
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES, type=Path)
    parser.add_argument("--manual", default=DEFAULT_MANUAL, type=Path)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, type=Path)
    parser.add_argument("--skip-overseas", action="store_true", help="Only build domestic/manual signals")
    args = parser.parse_args()

    candidates = read_csv(args.candidates)
    signals: List[Dict[str, str]] = []
    if not args.skip_overseas:
        signals.extend(collect_overseas_signals())
    signals.extend(collect_domestic_confirmation(candidates))
    signals.extend(normalize_manual_signals(args.manual))
    write_signals(args.output, signals)
    print(f"Theme signals: {len(signals)}")
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    main()
