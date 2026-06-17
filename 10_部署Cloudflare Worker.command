#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "部署 Cloudflare Worker"
echo
echo "这个脚本会部署 work/cloud/github_pages_refresh_worker.js。"
echo "需要本机已经登录 Cloudflare Wrangler，或已经配置 CLOUDFLARE_API_TOKEN。"
echo

if ! command -v npx >/dev/null 2>&1; then
  echo "当前系统没有 npx。请先安装 Node.js，或在 Cloudflare 网页控制台手动粘贴 Worker 代码。"
  echo
  echo "按回车关闭窗口。"
  read
  exit 1
fi

echo "正在部署..."
npx wrangler deploy

echo
echo "部署完成后，请确认 Worker 地址仍是："
cat work/cloud/refresh_endpoint.txt
echo
echo "固定链接："
echo "https://alexsheng666-bit.github.io/codex-A/outputs/stock_report.html"
echo
echo "按回车关闭窗口。"
read
