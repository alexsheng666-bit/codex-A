#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "配置固定链接里的“刷新数据”按钮"
echo
echo "请先在 Cloudflare Worker 部署完成后，把 Worker 公开地址粘贴到这里。"
echo "示例：https://codex-a-refresh.xxxxx.workers.dev"
echo
printf "Worker 地址: "
read WORKER_URL

if [ -z "$WORKER_URL" ]; then
  echo
  echo "没有输入地址，已取消。"
  echo "按回车关闭窗口。"
  read
  exit 1
fi

case "$WORKER_URL" in
  https://*)
    ;;
  *)
    echo
    echo "地址必须以 https:// 开头，请检查后重新运行。"
    echo "按回车关闭窗口。"
    read
    exit 1
    ;;
esac

mkdir -p work/cloud
printf "%s\n" "$WORKER_URL" > work/cloud/refresh_endpoint.txt

echo
echo "已保存刷新接口：$WORKER_URL"
echo "正在重新生成看板..."
python3 work/scripts/build_dashboard.py \
  --input work/normalized_data/candidates_latest.csv \
  --output dashboard/index.html

echo
echo "正在发布到固定 GitHub Pages 链接..."
if python3 work/scripts/publish_github_pages.py --commit --push --publish-cloud-source; then
  echo
  echo "已发布。现在固定链接里的“刷新数据”按钮会调用云端刷新接口。"
  echo "https://alexsheng666-bit.github.io/codex-A/outputs/stock_report.html"
else
  echo
  echo "普通发布没有完成。建议在下面粘贴 GitHub token；输入时不会显示。"
  echo "使用 token 时只会更新网页和运行必需文件。"
  echo "不想输入 token，直接按回车跳过。"
  printf "GitHub token: "
  stty -echo
  read GITHUB_TOKEN
  stty echo
  echo
  if [ -n "$GITHUB_TOKEN" ]; then
    export GITHUB_TOKEN
    if python3 work/scripts/publish_github_pages.py --commit --push --token-env GITHUB_TOKEN --publish-cloud-source; then
      echo
      echo "已发布。现在固定链接里的“刷新数据”按钮会调用云端刷新接口。"
      echo "https://alexsheng666-bit.github.io/codex-A/outputs/stock_report.html"
    else
      echo
      echo "使用 token 发布仍未完成。请检查 token 权限或网络。"
    fi
    unset GITHUB_TOKEN
  else
    echo "已跳过 token 发布。"
  fi
fi

echo
echo "完成。按回车关闭窗口。"
read
