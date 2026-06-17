#!/usr/bin/env python3
"""Refresh market data, candidate pools, and dashboard files."""

from __future__ import annotations

import argparse
import json
import sys

from serve_dashboard import refresh_dashboard


def print_summary(result: dict) -> None:
    summary = result.get("summary", {})
    print(result.get("message", "刷新完成。"))
    print(
        "刷新摘要: "
        f"来源 {summary.get('source', '-')}"
        f" | 交易日 {summary.get('trade_date', '-')}"
        f" | 采集 {summary.get('rows', 0)}"
        f" | 规则命中 {summary.get('raw_candidate_count', 0)}"
        f" | 入池 {summary.get('candidate_rows', 0)}"
        f" | 股票池 {summary.get('universe_cache', 0)}"
        f" | 复盘 {summary.get('review_rows', 0)}"
    )
    if summary.get("fallback"):
        print(f"提醒: 已启用降级兜底。{summary.get('fallback_note', '')}")
    if not result.get("ok"):
        print("刷新日志:")
        for item in result.get("logs", []):
            print(f"- {item.get('command')} -> {item.get('returncode')}")
            if item.get("stderr"):
                print(item["stderr"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh A-share dashboard data once.")
    parser.add_argument("--json", action="store_true", help="Output full refresh result as JSON.")
    args = parser.parse_args()

    result = refresh_dashboard()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_summary(result)
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
