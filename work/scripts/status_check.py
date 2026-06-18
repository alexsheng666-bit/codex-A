#!/usr/bin/env python3
"""Print a concise local status report for the A-share dashboard."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from rules_config import screening_config


ROOT = Path(__file__).resolve().parents[2]
LATEST_RAW = ROOT / "01_原始资料" / "market_data" / "raw_csv" / "latest_market_data.csv"
CANDIDATES = ROOT / "work" / "normalized_data" / "candidates_latest.csv"
UNIVERSE_CACHE = ROOT / "work" / "cache" / "stock_universe.csv"
MANUAL_EXPORTS = ROOT / "01_原始资料" / "market_data" / "manual_exports"
DASHBOARD = ROOT / "dashboard" / "index.html"
COVERAGE_BASIC_ROWS = 1500
COVERAGE_FULL_ROWS = 3000
RAW_MIN_ROWS = 3000

SOURCE_LABELS = {
    "ths_q_hs_snapshot": "同花顺行情列表",
    "ths_q_hs_snapshot_partial": "同花顺行情列表局部",
    "eastmoney_push2_snapshot": "东方财富行情快照",
    "sina_hq_universe_snapshot": "本地股票池 + 新浪行情",
    "sina_hq_focus_snapshot": "新浪重点样本",
    "akshare_stock_zh_a_spot_em": "AKShare 行情快照",
}


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def mtime(path: Path) -> str:
    if not path.exists():
        return "-"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def source_label(source: str) -> str:
    if source.startswith("ths_manual_export:"):
        return "同花顺手动导入"
    return SOURCE_LABELS.get(source, source or "未知来源")


def manual_export_files() -> List[str]:
    if not MANUAL_EXPORTS.exists():
        return []
    return sorted(
        path.name
        for path in MANUAL_EXPORTS.iterdir()
        if path.suffix.lower() in {".csv", ".xlsx", ".xls"} and not path.name.startswith(".")
    )


def coverage_status(cache_rows: int) -> str:
    if cache_rows >= COVERAGE_FULL_ROWS:
        return "接近全量"
    if cache_rows >= COVERAGE_BASIC_ROWS:
        return "基本可用"
    return "覆盖偏窄"


def raw_health_status(raw_rows: int) -> str:
    if raw_rows >= RAW_MIN_ROWS:
        return "采集达标"
    if raw_rows >= COVERAGE_BASIC_ROWS:
        return "采集不足"
    return "采集异常"


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


def raw_candidate_count(rows: List[Dict[str, str]]) -> int:
    return sum(
        1
        for row in rows
        if row.get("pool_raw_level") in {"A", "B", "C"} or row.get("pool_level") in {"A", "B", "C"}
    )


def build_status() -> Dict[str, object]:
    raw_rows = read_csv(LATEST_RAW)
    candidate_rows = read_csv(CANDIDATES)
    cache_rows = read_csv(UNIVERSE_CACHE)
    source_counts = Counter(row.get("data_source", "") for row in raw_rows)
    pool_counts = Counter(row.get("pool_level", "") for row in candidate_rows)
    trade_dates = sorted({row.get("trade_date", "") for row in raw_rows if row.get("trade_date")})
    trade_date = trade_dates[-1] if trade_dates else ""
    exports = manual_export_files()
    return {
        "trade_date": trade_date,
        **freshness_info(trade_date),
        "raw_rows": len(raw_rows),
        "raw_health_status": raw_health_status(len(raw_rows)),
        "raw_health_min_rows": RAW_MIN_ROWS,
        "eligible_rows": sum(1 for row in candidate_rows if row.get("universe_eligible") == "是"),
        "raw_candidate_count": raw_candidate_count(candidate_rows),
        "candidate_rows": len([row for row in candidate_rows if row.get("pool_level") in {"A", "B", "C"}]),
        "total_candidate_file_rows": len(candidate_rows),
        "pool_counts": {
            "重点关注": pool_counts.get("A", 0),
            "观察候补": pool_counts.get("B", 0),
            "题材异动记录": pool_counts.get("C", 0),
        },
        "universe_cache_rows": len(cache_rows),
        "coverage_status": coverage_status(len(cache_rows)),
        "source_counts": [(source_label(source), count) for source, count in source_counts.most_common()],
        "manual_export_files": exports,
        "latest_raw_updated_at": mtime(LATEST_RAW),
        "candidates_updated_at": mtime(CANDIDATES),
        "dashboard_updated_at": mtime(DASHBOARD),
        "dashboard_exists": DASHBOARD.exists(),
        "config": screening_config(),
    }


def print_text(status: Dict[str, object]) -> None:
    print("A股短线助手状态")
    print("-" * 28)
    print(f"最近交易日: {status['trade_date'] or '-'}")
    print(f"数据新鲜度: {status['freshness_status']}")
    print(f"原始采集: {status['raw_rows']} 行（{status['raw_health_status']}，稳定线 {status['raw_health_min_rows']}）")
    print(f"有效主板: {status['eligible_rows']} 行")
    print(f"规则命中: {status['raw_candidate_count']} 只")
    print(f"最终候选: {status['candidate_rows']} 只")
    pools = status["pool_counts"]
    print(f"重点关注: {pools['重点关注']} | 观察候补: {pools['观察候补']} | 题材异动记录: {pools['题材异动记录']}")
    print(f"股票池缓存: {status['universe_cache_rows']} 支")
    print(f"覆盖状态: {status['coverage_status']}")
    config = status["config"]
    caps = config["pool_caps"]
    print(f"规则配置: {config['status']} ({config['rules_path']})")
    print(f"入池上限: A{caps['A']} | B{caps['B']} | C{caps['C']}")
    print("重点主题: " + "，".join(config["theme_names"] or ["无"]))
    for warning in config["warnings"]:
        print(f"配置提醒: {warning}")
    sources = status["source_counts"] or [("无", 0)]
    print("数据来源: " + "，".join(f"{name} {count}" for name, count in sources))
    exports = status["manual_export_files"]
    print(f"同花顺导出文件: {len(exports)} 个" + (f" ({', '.join(exports[:3])})" if exports else ""))
    print(f"原始数据更新时间: {status['latest_raw_updated_at']}")
    print(f"候选池更新时间: {status['candidates_updated_at']}")
    print(f"看板更新时间: {status['dashboard_updated_at']}")
    print(f"看板文件: {'已生成' if status['dashboard_exists'] else '缺失'}")
    if status["freshness_status"] != "今日数据":
        print(f"提醒: {status['freshness_note']}")
    if status["coverage_status"] == "覆盖偏窄":
        print("提醒: 当前缓存不是全沪深主板，建议导入同花顺沪深主板列表后再刷新。")
    if status["raw_health_status"] != "采集达标":
        print("提醒: 原始采集低于 3000 行，本轮不建议作为最终推荐依据。")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show local dashboard data status.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    args = parser.parse_args()

    status = build_status()
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print_text(status)


if __name__ == "__main__":
    main()
