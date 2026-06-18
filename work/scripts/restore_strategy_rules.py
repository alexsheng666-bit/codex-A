#!/usr/bin/env python3
"""List or safely restore strategy rule backups."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGET = ROOT / "work" / "rules" / "strategy_rules.json"
DEFAULT_BACKUP_DIR = ROOT / "work" / "rules" / "backups"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def backup_files(backup_dir: Path) -> list[Path]:
    if not backup_dir.exists():
        return []
    return sorted(
        (path for path in backup_dir.glob("strategy_rules_*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def resolve_backup(name: str, backup_dir: Path) -> Path:
    candidate = Path(name)
    if not candidate.is_absolute():
        candidate = backup_dir / candidate
    candidate = candidate.resolve()
    backup_root = backup_dir.resolve()
    if backup_root not in candidate.parents:
        raise SystemExit("只能从 work/rules/backups 目录恢复备份。")
    if not candidate.exists():
        raise SystemExit(f"备份文件不存在：{display_path(candidate)}")
    if candidate.suffix.lower() != ".json":
        raise SystemExit("只能恢复 .json 备份文件。")
    return candidate


def create_pre_restore_backup(target: Path, backup_dir: Path) -> Path:
    if not target.exists():
        raise SystemExit(f"当前规则文件不存在：{display_path(target)}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = backup_dir / f"strategy_rules_before_restore_{stamp}.json"
    shutil.copy2(target, output)
    return output


def list_backups(backup_dir: Path) -> None:
    files = backup_files(backup_dir)
    if not files:
        print("暂无规则备份。")
        return
    print("可用规则备份：")
    for path in files:
        size = path.stat().st_size
        mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"- {path.name} | {mtime} | {size} bytes")


def main() -> None:
    parser = argparse.ArgumentParser(description="List or restore strategy_rules.json backups.")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR, help="Backup folder")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="Rules JSON to restore into")
    parser.add_argument("--restore", help="Backup file name to restore from")
    parser.add_argument("--yes", action="store_true", help="Confirm restore and overwrite target")
    args = parser.parse_args()

    if not args.restore:
        list_backups(args.backup_dir)
        return
    if not args.yes:
        raise SystemExit("恢复会覆盖当前规则文件。确认恢复请追加 --yes。")

    backup = resolve_backup(args.restore, args.backup_dir)
    safety_backup = create_pre_restore_backup(args.target, args.backup_dir)
    shutil.copy2(backup, args.target)
    print(f"已恢复规则配置：{display_path(backup)} -> {display_path(args.target)}")
    print(f"恢复前已自动备份当前配置：{display_path(safety_backup)}")


if __name__ == "__main__":
    main()
