#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "A股短线助手启动前自检"
echo
python3 work/scripts/status_check.py
echo
python3 work/scripts/diagnose_deployment.py
echo
echo "自检完成。按回车关闭窗口。"
read
