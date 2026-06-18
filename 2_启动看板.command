#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "A股短线助手看板启动中..."
echo
python3 work/scripts/status_check.py
echo
python3 work/scripts/build_dashboard.py \
  --input work/normalized_data/candidates_latest.csv \
  --output dashboard/index.html

python3 work/scripts/serve_dashboard.py --host 0.0.0.0 --port 8765 --auto-port --reuse-existing
