#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "正在关闭 A股短线助手看板服务..."
echo "如果已经安装自动运行，服务可能会自动重启；要关闭自动运行请使用 6_关闭自动运行.command。"
echo
python3 work/scripts/stop_dashboard_servers.py
echo
echo "完成。按回车关闭窗口。"
read
