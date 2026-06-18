#!/usr/bin/env python3
"""Create a timestamped backup of the strategy rules JSON file."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "work" / "rules" / "strategy_rules.json"
DEFAULT_BACKUP_DIR = ROOT / "work" / "rules" / "backups"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup strategy_rules.json before manual tuning.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Rules JSON to back up")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR, help="Backup output folder")
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(f"规则文件不存在：{args.source}")

    args.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = args.backup_dir / f"{args.source.stem}_{stamp}{args.source.suffix}"
    shutil.copy2(args.source, target)

    try:
        display = target.relative_to(ROOT)
    except ValueError:
        display = target
    print(f"已备份规则配置：{display}")


if __name__ == "__main__":
    main()
