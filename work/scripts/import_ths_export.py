#!/usr/bin/env python3
"""Import Tonghuashun manual exports into the local stock universe cache."""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = ROOT / "01_原始资料" / "market_data" / "manual_exports"
UNIVERSE_CACHE = ROOT / "work" / "cache" / "stock_universe.csv"
COVERAGE_BASIC_ROWS = 1500
COVERAGE_FULL_ROWS = 2500

INCLUDE_PREFIXES = ("600", "601", "603", "605", "000", "001", "002", "003")
EXCLUDE_PREFIXES = ("300", "301", "688", "8", "4", "9")
FIELDNAMES = [
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

ALIASES = {
    "code": ["代码", "股票代码", "证券代码", "股票编号", "stock_code", "code"],
    "name": ["名称", "股票名称", "证券名称", "股票简称", "简称", "stock_name", "name"],
    "industry": ["行业", "所属行业", "细分行业", "申万行业", "同花顺行业", "industry"],
    "concepts": [
        "概念",
        "所属概念",
        "概念题材",
        "题材",
        "概念板块",
        "所属板块",
        "板块",
        "concepts",
    ],
}


def normalize_key(value: object) -> str:
    return re.sub(r"[\s_\-./()（）【】\\[\\]:：]+", "", str(value or "")).lower()


def clean_code(value: object) -> str:
    text = str(value or "").strip()
    match = re.search(r"(\d{6})", text)
    if match:
        return match.group(1)
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else ""


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


def split_tags(value: object) -> List[str]:
    text = str(value or "").strip()
    if not text:
        return []
    parts = re.split(r"[;,，；/、|｜\s]+", text)
    tags: List[str] = []
    seen = set()
    for part in parts:
        tag = part.strip()
        if not tag or tag in {"-", "--", "无", "nan", "None"}:
            continue
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def merge_tags(*values: object) -> str:
    tags: List[str] = []
    seen = set()
    for value in values:
        for tag in split_tags(value):
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return ";".join(tags)


def coverage_status(cache_rows: int) -> str:
    if cache_rows >= COVERAGE_FULL_ROWS:
        return "接近全量"
    if cache_rows >= COVERAGE_BASIC_ROWS:
        return "基本可用"
    return "覆盖偏窄"


def coverage_gap(cache_rows: int) -> str:
    if cache_rows < COVERAGE_BASIC_ROWS:
        return f"距离基本可用还差约 {COVERAGE_BASIC_ROWS - cache_rows} 支"
    if cache_rows < COVERAGE_FULL_ROWS:
        return f"距离接近全量还差约 {COVERAGE_FULL_ROWS - cache_rows} 支"
    return "已达到接近全量口径"


def read_cache(path: Path = UNIVERSE_CACHE) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return {clean_code(row.get("stock_code")): dict(row) for row in csv.DictReader(file) if row.get("stock_code")}


def write_cache(cache: Dict[str, Dict[str, str]], path: Path = UNIVERSE_CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(cache.values(), key=lambda row: row.get("stock_code", ""))
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in FIELDNAMES} for row in rows])


def read_csv_rows(path: Path) -> List[Dict[str, object]]:
    for encoding in ("utf-8-sig", "gbk", "gb18030"):
        try:
            with path.open("r", newline="", encoding=encoding) as file:
                return [dict(row) for row in csv.DictReader(file)]
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法识别文件编码: {path}")


def read_excel_rows(path: Path) -> List[Dict[str, object]]:
    import pandas as pd  # type: ignore

    frame = pd.read_excel(path)
    frame = frame.fillna("")
    return frame.to_dict("records")


def read_rows(path: Path) -> List[Dict[str, object]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv_rows(path)
    if suffix in {".xlsx", ".xls"}:
        return read_excel_rows(path)
    raise RuntimeError(f"暂不支持的文件类型: {path.suffix}")


def resolve_columns(rows: List[Dict[str, object]]) -> Dict[str, Optional[str]]:
    if not rows:
        return {key: None for key in ALIASES}
    columns = list(rows[0].keys())
    normalized = {normalize_key(column): column for column in columns}
    resolved: Dict[str, Optional[str]] = {}
    for field, aliases in ALIASES.items():
        resolved[field] = None
        for alias in aliases:
            column = normalized.get(normalize_key(alias))
            if column is not None:
                resolved[field] = column
                break
    return resolved


def pick(row: Dict[str, object], column: Optional[str]) -> object:
    if column is None:
        return ""
    return row.get(column, "")


def import_rows(rows: List[Dict[str, object]], source_name: str, dry_run: bool = False) -> Dict[str, int]:
    cache = read_cache()
    columns = resolve_columns(rows)
    if not columns.get("code") or not columns.get("name"):
        raise RuntimeError("导入文件至少需要包含股票代码和股票名称两列")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stats = {"input": len(rows), "imported": 0, "skipped": 0, "updated_cache": len(cache)}
    for row in rows:
        code = clean_code(pick(row, columns.get("code")))
        name = str(pick(row, columns.get("name")) or "").strip()
        if not is_main_board(code, name):
            stats["skipped"] += 1
            continue

        existing = cache.get(code, {})
        industry = str(pick(row, columns.get("industry")) or existing.get("industry") or "").strip()
        concepts = merge_tags(existing.get("concepts", ""), pick(row, columns.get("concepts")))
        cache[code] = {
            "stock_code": code,
            "stock_name": name or existing.get("stock_name", ""),
            "board": board_for(code),
            "market": market_for(code),
            "industry": industry,
            "concepts": concepts,
            "first_seen": existing.get("first_seen") or now,
            "last_seen": now,
            "data_source": source_name,
        }
        stats["imported"] += 1

    stats["updated_cache"] = len(cache)
    if not dry_run:
        write_cache(cache)
    return stats


def discover_inputs(input_path: Optional[Path]) -> List[Path]:
    if input_path:
        if input_path.is_dir():
            return sorted(
                path
                for path in input_path.iterdir()
                if path.suffix.lower() in {".csv", ".xlsx", ".xls"} and not path.name.startswith(".")
            )
        return [input_path]
    if not DEFAULT_INPUT_DIR.exists():
        return []
    return sorted(
        path
        for path in DEFAULT_INPUT_DIR.iterdir()
        if path.suffix.lower() in {".csv", ".xlsx", ".xls"} and not path.name.startswith(".")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Tonghuashun CSV/Excel exports into local stock universe.")
    parser.add_argument("--input", type=Path, help="Export file or folder. Defaults to manual_exports folder.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report only; do not write cache.")
    parser.add_argument("--allow-empty", action="store_true", help="Exit successfully when no export files exist.")
    args = parser.parse_args()

    inputs = discover_inputs(args.input)
    if not inputs:
        if args.allow_empty:
            print(f"No import files found: {DEFAULT_INPUT_DIR}")
            return
        raise SystemExit(f"未找到导入文件，请放入: {DEFAULT_INPUT_DIR}")

    total_input = 0
    total_imported = 0
    total_skipped = 0
    cache_total = 0
    for path in inputs:
        rows = read_rows(path)
        stats = import_rows(rows, f"ths_manual_export:{path.name}", dry_run=args.dry_run)
        total_input += stats["input"]
        total_imported += stats["imported"]
        total_skipped += stats["skipped"]
        cache_total = stats["updated_cache"]
        print(
            f"Imported {path.name}: input={stats['input']} imported={stats['imported']} "
            f"skipped={stats['skipped']} cache={stats['updated_cache']}"
        )

    mode = "DRY RUN" if args.dry_run else "DONE"
    print(f"{mode}: input={total_input} imported={total_imported} skipped={total_skipped} cache={cache_total}")
    print(f"Coverage: {coverage_status(cache_total)}，{coverage_gap(cache_total)}")


if __name__ == "__main__":
    main()
