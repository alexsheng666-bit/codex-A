#!/usr/bin/env python3
"""Enrich raw market snapshot with less-approximate strategy signals."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import Dict, List


def yes(value: bool) -> str:
    return "是" if value else "否"


def num(row: Dict[str, str], key: str, default: float = 0.0) -> float:
    raw = str(row.get(key, "")).strip().replace(",", "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def split_tags(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").replace("；", ";").split(";") if item.strip()]


def row_themes(row: Dict[str, str]) -> List[str]:
    themes = split_tags(row.get("concepts", "")) + split_tags(row.get("theme_tags", ""))
    industry = str(row.get("industry", "")).strip()
    if industry:
        themes.append(industry)
    seen = set()
    result = []
    for theme in themes:
        if theme and theme not in seen:
            seen.add(theme)
            result.append(theme)
    return result


def vwap_price(row: Dict[str, str]) -> float:
    amount = num(row, "turnover_amount")
    volume = num(row, "volume")
    close = num(row, "close")
    if amount <= 0 or volume <= 0 or close <= 0:
        return 0.0

    candidates = [amount / volume, amount / (volume * 100)]
    for value in candidates:
        if close * 0.3 <= value <= close * 3:
            return round(value, 2)
    return 0.0


def has_minute_tail_source(row: Dict[str, str]) -> bool:
    source = str(row.get("data_source", "")).lower()
    note = str(row.get("manual_note", "")).lower()
    text = f"{source} {note}"
    if "近似" in note or "日线" in note:
        return False
    return any(marker in text for marker in ("minute", "1m", "5m", "intraday", "分时", "分钟"))


def enrich_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    theme_limit_counts: Counter[str] = Counter()
    for row in rows:
        is_limit_up = str(row.get("limit_up_status", "")).strip() == "是" or num(row, "pct_change") >= 9.7
        if not is_limit_up:
            continue
        for theme in row_themes(row):
            theme_limit_counts[theme] += 1

    ranked_themes = {theme: index + 1 for index, (theme, _) in enumerate(theme_limit_counts.most_common())}

    for row in rows:
        themes = row_themes(row)
        counts = [theme_limit_counts.get(theme, 0) for theme in themes]
        ranks = [ranked_themes.get(theme, 99) for theme in themes if theme in ranked_themes]
        real_count = max(counts) if counts else 0
        real_rank = min(ranks) if ranks else 99

        vwap = vwap_price(row)
        close = num(row, "close")
        real_tail = has_minute_tail_source(row)

        row["vwap_price"] = f"{vwap:.2f}" if vwap else ""
        row["above_intraday_vwap"] = yes(bool(vwap and close >= vwap))
        row["vwap_signal_source"] = "成交额/成交量推算" if vwap else ""
        row["real_board_limit_up_count"] = str(real_count)
        row["real_theme_limit_up_count"] = str(real_count)
        row["theme_limit_up_count"] = str(real_count)
        row["theme_rank"] = str(real_rank)
        row["theme_tail_reflow"] = yes(real_count >= 3 and num(row, "pct_change") >= 2 and num(row, "volume_ratio") >= 1.1)
        row["real_tail_volume_confirmed"] = yes(real_tail)
        row["tail_signal_source"] = "真实分钟级尾盘量" if real_tail else "非分钟级数据，尾盘量未确认"
        if real_tail:
            row["tail_volume_confirmed"] = "是"
        else:
            row["tail_volume_confirmed"] = "否"
    return rows


def read_csv(path: Path) -> List[Dict[str, str]]:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich raw A-share data with strategy signals.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rows = enrich_rows(read_csv(args.input))
    write_csv(args.output, rows)
    real_tail_count = sum(1 for row in rows if row.get("real_tail_volume_confirmed") == "是")
    real_limit_themes = sum(1 for row in rows if num(row, "real_theme_limit_up_count") >= 3)
    print(f"Enriched rows: {len(rows)}")
    print(f"Real tail minute confirmations: {real_tail_count}")
    print(f"Rows with theme limit-up count >= 3: {real_limit_themes}")


if __name__ == "__main__":
    main()
