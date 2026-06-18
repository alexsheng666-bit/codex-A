#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "准备关闭 A股短线助手自动运行..."
echo
work/automation/uninstall_dashboard_automation.sh
echo
echo "完成。按回车关闭窗口。"
read
