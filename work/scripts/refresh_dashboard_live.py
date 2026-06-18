#!/usr/bin/env python3
"""Refresh dashboard data with visible progress for manual terminal use."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_step(title: str, args: list[str], timeout: int = 180, optional: bool = False) -> None:
    print(f"\n{title}", flush=True)
    print("-" * 36, flush=True)
    try:
        completed = subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        message = f"{title} 超时。"
        if optional:
            print(f"{message} 已跳过，继续使用现有本地缓存。", flush=True)
            return
        raise SystemExit(f"{message} 当前网络可能较慢，请稍后重试。") from error
    if completed.returncode != 0:
        if optional:
            print(f"{title} 未完成。已跳过，继续后续刷新。", flush=True)
            return
        raise SystemExit(f"{title} 失败，请把上方错误内容发给我。")


def main() -> None:
    print("开始刷新：行情、筛选、复盘和看板会逐项执行。", flush=True)

    run_step(
        "1/8 扩容股票池",
        ["work/scripts/sync_exchange_universe.py", "--allow-fail"],
        timeout=45,
        optional=True,
    )
    run_step(
        "2/8 导入同花顺导出文件",
        ["work/scripts/import_ths_export.py", "--allow-empty"],
        optional=True,
    )
    run_step(
        "3/8 获取最新行情",
        [
            "work/scripts/fetch_latest_demo_data.py",
            "--output",
            "01_原始资料/market_data/raw_csv/latest_market_data.csv",
        ],
        timeout=240,
    )
    run_step(
        "4/8 增强真实信号",
        [
            "work/scripts/enrich_market_signals.py",
            "--input",
            "01_原始资料/market_data/raw_csv/latest_market_data.csv",
            "--output",
            "01_原始资料/market_data/raw_csv/latest_market_data.csv",
        ],
    )
    run_step(
        "5/8 筛选候选池",
        [
            "work/scripts/screen_candidates.py",
            "--input",
            "01_原始资料/market_data/raw_csv/latest_market_data.csv",
            "--output-csv",
            "work/normalized_data/candidates_latest.csv",
            "--report",
            "work/reports/candidates_latest.md",
            "--report-html",
            "work/reports/candidates_latest.html",
        ],
    )
    run_step(
        "6/8 次日自动复盘",
        [
            "work/scripts/review_next_day.py",
            "--candidates",
            "work/normalized_data/candidates_latest.csv",
            "--market",
            "01_原始资料/market_data/raw_csv/latest_market_data.csv",
            "--output",
            "work/review/next_day_review_latest.csv",
            "--report",
            "work/review/next_day_review_latest.md",
        ],
    )
    run_step(
        "7/8 更新模拟交易账户",
        [
            "work/scripts/update_paper_trading.py",
            "--candidates",
            "work/normalized_data/candidates_latest.csv",
            "--market",
            "01_原始资料/market_data/raw_csv/latest_market_data.csv",
        ],
    )
    run_step(
        "8/8 生成看板文件",
        [
            "work/scripts/build_dashboard.py",
            "--input",
            "work/normalized_data/candidates_latest.csv",
            "--output",
            "dashboard/index.html",
        ],
    )
    run_step("刷新后状态", ["work/scripts/status_check.py"], timeout=60)
    print("\n刷新完成，可以继续发布到 GitHub Pages。", flush=True)


if __name__ == "__main__":
    main()
