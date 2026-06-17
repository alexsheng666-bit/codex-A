#!/usr/bin/env python3
"""Review previous A-pool candidates against the latest market snapshot."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = ROOT / "work" / "review" / "candidate_snapshots"
DEFAULT_CANDIDATES = ROOT / "work" / "normalized_data" / "candidates_latest.csv"
DEFAULT_MARKET = ROOT / "01_原始资料" / "market_data" / "raw_csv" / "latest_market_data.csv"
DEFAULT_OUTPUT = ROOT / "work" / "review" / "next_day_review_latest.csv"
DEFAULT_REPORT = ROOT / "work" / "review" / "next_day_review_latest.md"


def num(row: Dict[str, str], key: str, default: float = 0.0) -> float:
    raw = str(row.get(key, "")).strip().replace(",", "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def trade_date(rows: List[Dict[str, str]]) -> str:
    dates = sorted({row.get("trade_date", "") for row in rows if row.get("trade_date")})
    return dates[-1] if dates else ""


def archive_current(candidates_path: Path) -> Path:
    rows = read_csv(candidates_path)
    date = trade_date(rows) or datetime.now().strftime("%Y-%m-%d")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    target = ARCHIVE_DIR / f"candidates_{date}.csv"
    write_csv(target, rows)
    return target


def previous_snapshot(current_date: str) -> Path | None:
    if not ARCHIVE_DIR.exists():
        return None
    files = sorted(ARCHIVE_DIR.glob("candidates_*.csv"))
    candidates = [path for path in files if path.stem.replace("candidates_", "") < current_date]
    return candidates[-1] if candidates else None


def review(previous_rows: List[Dict[str, str]], market_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    market_by_code = {row.get("stock_code", ""): row for row in market_rows}
    current_date = trade_date(market_rows)
    output = []
    for row in previous_rows:
        if row.get("pool_level") != "A":
            continue
        quote = market_by_code.get(row.get("stock_code", ""))
        if not quote:
            continue
        buy = num(row, "buy_point") or num(row, "close")
        first_take = num(row, "first_take_profit_point") or num(row, "sell_point")
        stop = num(row, "defensive_stop_point") or num(row, "stop_point")
        close = num(quote, "close")
        high = num(quote, "high", close)
        low = num(quote, "low", close)
        open_price = num(quote, "open", close)
        pct_from_buy = round((close - buy) / buy * 100, 2) if buy else 0

        hit_take = bool(first_take and high >= first_take)
        hit_stop = bool(stop and low <= stop)
        if hit_take and hit_stop:
            result = "先后触发待人工核对"
        elif hit_take:
            result = "触发第一止盈"
        elif hit_stop:
            result = "触发防守止损"
        elif close > buy:
            result = "浮盈未触发第一止盈"
        else:
            result = "走弱需按时间止损复核"

        output.append(
            {
                "review_date": current_date,
                "entry_date": row.get("trade_date", ""),
                "stock_code": row.get("stock_code", ""),
                "stock_name": row.get("stock_name", ""),
                "buy_point": f"{buy:.2f}" if buy else "",
                "first_take_profit_point": f"{first_take:.2f}" if first_take else "",
                "defensive_stop_point": f"{stop:.2f}" if stop else "",
                "next_open": f"{open_price:.2f}" if open_price else "",
                "next_high": f"{high:.2f}" if high else "",
                "next_low": f"{low:.2f}" if low else "",
                "next_close": f"{close:.2f}" if close else "",
                "return_from_buy_pct": pct_from_buy,
                "review_result": result,
            }
        )
    return output


def write_report(path: Path, rows: List[Dict[str, str]]) -> None:
    lines = ["# 次日自动复盘", "", f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    if not rows:
        lines.extend(["暂无可复盘的上一交易日 A 池记录。", ""])
    else:
        lines.append("| 股票 | 买入 | 第一止盈 | 防守止损 | 今开 | 最高 | 最低 | 最新 | 收益 | 结论 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for row in rows:
            lines.append(
                f"| {row.get('stock_code')} {row.get('stock_name')} | {row.get('buy_point')} | "
                f"{row.get('first_take_profit_point')} | {row.get('defensive_stop_point')} | "
                f"{row.get('next_open')} | {row.get('next_high')} | {row.get('next_low')} | "
                f"{row.get('next_close')} | {row.get('return_from_buy_pct')}% | {row.get('review_result')} |"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Review previous A-pool candidates.")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--market", type=Path, default=DEFAULT_MARKET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    market_rows = read_csv(args.market)
    current_date = trade_date(market_rows)
    previous = previous_snapshot(current_date)
    rows = review(read_csv(previous), market_rows) if previous else []
    write_csv(args.output, rows)
    write_report(args.report, rows)
    archived = archive_current(args.candidates)
    print(f"Review rows: {len(rows)}")
    print(f"Archived current candidates: {archived}")
    print(f"Wrote review: {args.output}")


if __name__ == "__main__":
    main()
