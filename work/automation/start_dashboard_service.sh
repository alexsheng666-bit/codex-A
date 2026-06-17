#!/bin/zsh
set -e

ROOT="/Users/alexsheng/Documents/A股短线助手"
cd "$ROOT"

mkdir -p work/logs

python3 work/scripts/stop_dashboard_servers.py || true

python3 work/scripts/build_dashboard.py \
  --input work/normalized_data/candidates_latest.csv \
  --output dashboard/index.html

exec python3 work/scripts/serve_dashboard.py --host 0.0.0.0 --port 8765 --auto-port
