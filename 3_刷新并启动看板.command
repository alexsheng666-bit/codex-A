#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "A股短线助手看板启动中..."
echo "先刷新数据，再启动看板。网络较慢时请稍等。"
echo
echo "步骤 1/3：启动前状态检查"
python3 work/scripts/status_check.py
echo
echo "步骤 2/3：刷新行情、筛选、复盘和看板"
python3 work/scripts/refresh_dashboard_data.py
echo
echo "步骤 3/3：刷新后状态检查"
python3 work/scripts/status_check.py
echo
echo "正在启动本地看板服务，看到 Local 或 LAN 链接后即可打开查看。"
python3 work/scripts/serve_dashboard.py --host 0.0.0.0 --port 8765 --auto-port --reuse-existing
