#!/bin/zsh
set -e

ROOT="${CODEXA_ROOT:-/Users/alexsheng/Documents/A股短线助手}"
LOG_DIR="$HOME/Library/Logs/CodexA"
RUN_LOG="$LOG_DIR/dashboard_refresh.run.log"
LOCK_DIR="$ROOT/work/cache/refresh_dashboard.lock"
mkdir -p "$LOG_DIR"

log_line() {
  echo "[$(date '+%F %T')] $*"
}

{
  log_line "自动刷新启动"
  log_line "项目目录：$ROOT"
  log_line "执行用户：$(id -un)"
  log_line "PATH：$PATH"
} >> "$RUN_LOG"

finish() {
  code=$?
  rmdir "$LOCK_DIR" 2>/dev/null || true
  log_line "自动刷新结束，退出码：$code" >> "$RUN_LOG"
  exit $code
}
trap finish EXIT

cd "$ROOT"

mkdir -p work/logs
mkdir -p work/cache

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log_line "已有刷新任务正在运行，本次自动刷新跳过。" | tee -a "$RUN_LOG"
  exit 0
fi

python3 work/scripts/refresh_dashboard_data.py

python3 work/scripts/publish_github_pages.py

PUBLISH_CLONE="$ROOT/work/codex_publish_clone"
if [ ! -d "$PUBLISH_CLONE/.git" ]; then
  log_line "GitHub Pages 自动发布失败：发布仓库不存在：$PUBLISH_CLONE" | tee -a "$RUN_LOG"
  exit 0
fi

/usr/bin/rsync -a outputs/ "$PUBLISH_CLONE/outputs/"
[ -f .nojekyll ] && /bin/cp .nojekyll "$PUBLISH_CLONE/.nojekyll"
/usr/bin/git -C "$PUBLISH_CLONE" config user.name "Codex"
/usr/bin/git -C "$PUBLISH_CLONE" config user.email "codex@local"
/usr/bin/git -C "$PUBLISH_CLONE" add -f outputs/stock_report.html outputs/index.html outputs/publish_metadata.json .nojekyll
if ! /usr/bin/git -C "$PUBLISH_CLONE" diff --cached --quiet; then
  /usr/bin/git -C "$PUBLISH_CLONE" commit -m "Update stock report $(date '+%Y-%m-%d %H:%M')"
else
  log_line "GitHub Pages 输出没有变化，无需提交。" | tee -a "$RUN_LOG"
fi

if ! /usr/bin/git -C "$PUBLISH_CLONE" push; then
  log_line "GitHub Pages 自动发布失败：请确认 GitHub 登录状态、网络连接或仓库推送权限。" | tee -a "$RUN_LOG"
fi
