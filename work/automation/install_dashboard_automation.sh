#!/bin/zsh
set -e

ROOT="/Users/alexsheng/Documents/A股短线助手"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
SERVICE_LABEL="com.alexsheng.codex-a.dashboard.service"
REFRESH_LABEL="com.alexsheng.codex-a.dashboard.refresh"

mkdir -p "$LAUNCH_AGENTS" "$ROOT/work/logs"

cd "$ROOT"

python3 "$ROOT/work/scripts/stop_dashboard_servers.py" || true

cp "$ROOT/work/automation/$REFRESH_LABEL.plist" "$LAUNCH_AGENTS/$REFRESH_LABEL.plist"

launchctl unload "$LAUNCH_AGENTS/$SERVICE_LABEL.plist" >/dev/null 2>&1 || true
launchctl unload "$LAUNCH_AGENTS/$REFRESH_LABEL.plist" >/dev/null 2>&1 || true
rm -f "$LAUNCH_AGENTS/$SERVICE_LABEL.plist"

launchctl load "$LAUNCH_AGENTS/$REFRESH_LABEL.plist"

echo "自动运行已启用。"
echo "- 不再启动本地看板服务"
echo "- 周一至周五按交易节奏自动刷新并尝试发布：9:32、10:30、11:35、13:30、14:30、14:45、14:52、14:57、15:10、16:10"
echo
echo "固定 Pages 链接：https://alexsheng666-bit.github.io/codex-A/outputs/stock_report.html"
echo
echo "日志位置：$ROOT/work/logs/"
