#!/bin/zsh
set -e

ROOT="/Users/alexsheng/Documents/A股短线助手"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/CodexA"
RUNTIME_DIR="$HOME/Library/Application Support/CodexA"
RUNTIME_PROJECT="$RUNTIME_DIR/runtime_project"
WRAPPER="$RUNTIME_DIR/refresh_dashboard_once.sh"
SERVICE_LABEL="com.alexsheng.codex-a.dashboard.service"
REFRESH_LABEL="com.alexsheng.codex-a.dashboard.refresh"

mkdir -p "$LAUNCH_AGENTS" "$LOG_DIR" "$RUNTIME_DIR" "$ROOT/work/logs"

rm -f "$RUNTIME_DIR/project"

/usr/bin/rsync -a --delete \
  --exclude 'work/cache/refresh_dashboard.lock' \
  "$ROOT/" "$RUNTIME_PROJECT/"

cat > "$WRAPPER" <<'EOF'
#!/bin/zsh
set -e

export LANG="zh_CN.UTF-8"
export LC_ALL="zh_CN.UTF-8"

ROOT="$HOME/Library/Application Support/CodexA/runtime_project"
LOG_DIR="$HOME/Library/Logs/CodexA"
RUN_LOG="$LOG_DIR/dashboard_refresh.run.log"
LOCK_DIR="$ROOT/work/cache/refresh_dashboard.lock"

mkdir -p "$LOG_DIR"

log_line() {
  echo "[$(date '+%F %T')] $*"
}

{
  log_line "自动刷新启动"
  log_line "项目入口：$ROOT"
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

/usr/bin/python3 work/scripts/refresh_dashboard_data.py

/usr/bin/python3 work/scripts/publish_github_pages.py

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
EOF
chmod +x "$WRAPPER"

cd "$ROOT"

python3 "$ROOT/work/scripts/stop_dashboard_servers.py" || true

cp "$ROOT/work/automation/$REFRESH_LABEL.plist" "$LAUNCH_AGENTS/$REFRESH_LABEL.plist"

launchctl unload "$LAUNCH_AGENTS/$SERVICE_LABEL.plist" >/dev/null 2>&1 || true
launchctl unload "$LAUNCH_AGENTS/$REFRESH_LABEL.plist" >/dev/null 2>&1 || true
rm -f "$LAUNCH_AGENTS/$SERVICE_LABEL.plist"

launchctl load "$LAUNCH_AGENTS/$REFRESH_LABEL.plist"

echo "自动运行已启用。"
echo "- 不再启动本地看板服务"
echo "- 周一至周五按交易节奏自动刷新并尝试发布：9:32、10:30、11:25、13:30、14:15、14:35、14:45、14:50、14:55、15:10、16:10"
echo
echo "固定 Pages 链接：https://alexsheng666-bit.github.io/codex-A/outputs/stock_report.html"
echo
echo "自动运行日志位置：$LOG_DIR/"
echo "项目内部日志位置：$ROOT/work/logs/"
echo "自动运行入口：$WRAPPER"
echo "自动运行副本：$RUNTIME_PROJECT"
