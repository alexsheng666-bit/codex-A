#!/usr/bin/env python3
"""Sync official SSE/SZSE stock lists into the local stock universe cache."""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
UNIVERSE_CACHE = ROOT / "work" / "cache" / "stock_universe.csv"

INCLUDE_PREFIXES = ("600", "601", "603", "605", "000", "001", "002", "003")
EXCLUDE_PREFIXES = ("300", "301", "688", "8", "4", "9")
COVERAGE_BASIC_ROWS = 1500
COVERAGE_FULL_ROWS = 2500
EASTMONEY_HOSTS = [
    "push2.eastmoney.com",
    "82.push2.eastmoney.com",
    "48.push2.eastmoney.com",
    "32.push2.eastmoney.com",
]
EASTMONEY_FIELDS = "f12,f14,f13,f100"
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


def fetch_exchange_rows() -> List[Dict[str, str]]:
    import akshare as ak  # type: ignore

    rows: List[Dict[str, str]] = []

    sh = ak.stock_info_sh_name_code(symbol="主板A股")
    for item in sh.to_dict("records"):
        code = clean_code(item.get("证券代码"))
        name = str(item.get("证券简称") or "").strip()
        if is_main_board(code, name):
            rows.append(
                {
                    "stock_code": code,
                    "stock_name": name,
                    "board": "沪主板",
                    "market": "SH",
                    "industry": "",
                    "concepts": "",
                }
            )

    sz = ak.stock_info_sz_name_code(symbol="A股列表")
    for item in sz.to_dict("records"):
        code = clean_code(item.get("A股代码"))
        name = str(item.get("A股简称") or "").strip()
        board = str(item.get("板块") or "").strip()
        if board == "创业板":
            continue
        if is_main_board(code, name):
            rows.append(
                {
                    "stock_code": code,
                    "stock_name": name,
                    "board": "深主板",
                    "market": "SZ",
                    "industry": str(item.get("所属行业") or "").strip(),
                    "concepts": "",
                }
            )
    return rows


def request_eastmoney_page(host: str, page: int, page_size: int) -> Dict[str, object]:
    query = {
        "pn": page,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "fltt": 2,
        "invt": 2,
        "fid": "f12",
        "fs": "m:1+t:2,m:0+t:6",
        "fields": EASTMONEY_FIELDS,
    }
    url = f"https://{host}/api/qt/clist/get?{urlencode(query)}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
    with urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_eastmoney_rows(page_size: int = 500, max_pages: int = 20) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    total = 0
    last_error: Exception | None = None
    for page in range(1, max_pages + 1):
        page_data = None
        for host in EASTMONEY_HOSTS:
            try:
                page_data = request_eastmoney_page(host, page, page_size)
                break
            except Exception as exc:
                last_error = exc
        if page_data is None:
            if rows:
                print(f"Eastmoney universe stopped at page {page}; using partial list with {len(rows)} rows")
                break
            raise RuntimeError(f"Eastmoney universe fetch failed: {last_error}")
        body = page_data.get("data") or {}
        page_rows = body.get("diff") or []
        if not isinstance(page_rows, list) or not page_rows:
            break
        total = int(body.get("total") or total or 0)
        for item in page_rows:
            code = clean_code(item.get("f12"))
            name = str(item.get("f14") or "").strip()
            if not is_main_board(code, name):
                continue
            rows.append(
                {
                    "stock_code": code,
                    "stock_name": name,
                    "board": board_for(code),
                    "market": market_for(code),
                    "industry": str(item.get("f100") or "").strip(),
                    "concepts": "",
                }
            )
        print(f"Fetched Eastmoney universe page {page}: eligible so far {len(rows)}")
        if total and page * page_size >= total:
            break
        time.sleep(0.12)
    if not rows:
        raise RuntimeError("Eastmoney universe returned no eligible rows")
    return rows


def update_cache(rows: Iterable[Dict[str, str]], dry_run: bool = False) -> Dict[str, int]:
    cache = read_cache()
    before = len(cache)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    imported = 0
    for row in rows:
        code = clean_code(row.get("stock_code"))
        name = str(row.get("stock_name") or "").strip()
        if not is_main_board(code, name):
            continue
        existing = cache.get(code, {})
        cache[code] = {
            "stock_code": code,
            "stock_name": name or existing.get("stock_name", ""),
            "board": row.get("board") or board_for(code),
            "market": row.get("market") or market_for(code),
            "industry": row.get("industry") or existing.get("industry", ""),
            "concepts": existing.get("concepts", "") or row.get("concepts", ""),
            "first_seen": existing.get("first_seen") or now,
            "last_seen": now,
            "data_source": "exchange_official_list",
        }
        imported += 1
    if not dry_run:
        write_cache(cache)
    return {"before": before, "imported": imported, "cache": len(cache)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync SSE/SZSE official stock lists into local universe cache.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report only; do not write cache.")
    parser.add_argument("--allow-fail", action="store_true", help="Exit successfully if official list fetch fails.")
    args = parser.parse_args()

    try:
        try:
            rows = fetch_exchange_rows()
            provider = "exchange_official_list"
        except Exception as official_exc:
            print(f"Official exchange list failed, falling back to Eastmoney universe: {official_exc}")
            rows = fetch_eastmoney_rows()
            provider = "eastmoney_universe_list"
        stats = update_cache(rows, dry_run=args.dry_run)
    except Exception as exc:
        message = f"Exchange universe sync failed: {exc}"
        if args.allow_fail:
            print(message)
            return
        raise SystemExit(message)

    mode = "DRY RUN" if args.dry_run else "DONE"
    print(
        f"{mode}: provider={provider} fetched={len(rows)} imported={stats['imported']} "
        f"cache_before={stats['before']} cache={stats['cache']}"
    )
    print(f"Coverage: {coverage_status(stats['cache'])}，{coverage_gap(stats['cache'])}")


if __name__ == "__main__":
    main()
