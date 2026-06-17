#!/bin/zsh
set -e

ROOT="/Users/alexsheng/Documents/A股短线助手"
cd "$ROOT"

mkdir -p work/logs
mkdir -p work/cache

LOCK_DIR="work/cache/refresh_dashboard.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "已有刷新任务正在运行，本次自动刷新跳过。"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

python3 work/scripts/refresh_dashboard_data.py

if ! python3 work/scripts/publish_github_pages.py --commit --push; then
  echo "GitHub Pages 自动发布失败：请确认 GitHub 登录状态、网络连接或仓库推送权限。"
fi
