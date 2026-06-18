#!/bin/zsh
set -e

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/CodexA"
RUNTIME_DIR="$HOME/Library/Application Support/CodexA"
RUNTIME_PROJECT="$RUNTIME_DIR/runtime_project"
SERVICE_LABEL="com.alexsheng.codex-a.dashboard.service"
REFRESH_LABEL="com.alexsheng.codex-a.dashboard.refresh"

launchctl unload "$LAUNCH_AGENTS/$SERVICE_LABEL.plist" >/dev/null 2>&1 || true
launchctl unload "$LAUNCH_AGENTS/$REFRESH_LABEL.plist" >/dev/null 2>&1 || true

rm -f "$LAUNCH_AGENTS/$SERVICE_LABEL.plist"
rm -f "$LAUNCH_AGENTS/$REFRESH_LABEL.plist"
rm -f "$RUNTIME_DIR/refresh_dashboard_once.sh"

echo "自动运行已关闭。"
echo "自动运行日志保留在：$LOG_DIR/"
echo "自动运行副本保留在：$RUNTIME_PROJECT/"
