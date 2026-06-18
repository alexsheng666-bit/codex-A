#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "正在发布 A股短线助手看板到 GitHub Pages..."
echo

if [ -d "$(git rev-parse --git-path rebase-merge 2>/dev/null)" ] || [ -d "$(git rev-parse --git-path rebase-apply 2>/dev/null)" ]; then
  echo "检测到 Git 仍处于同步中途状态。"
  echo "请先双击 0_修复Git同步状态.command，完成后再运行本发布入口。"
  echo
  echo "按回车关闭窗口。"
  read
  exit 1
fi

if python3 work/scripts/publish_github_pages.py --commit --push; then
  echo
  echo "固定访问链接："
  echo "https://alexsheng666-bit.github.io/codex-A/outputs/stock_report.html"
else
  echo
  echo "正常发布没有完成。常见原因："
  echo "1. 终端无法连接 github.com。"
  echo "2. 当前电脑还没有登录 GitHub。"
  echo "3. 仓库没有推送权限。"
  echo
  echo "如果普通 Git 推送失败，建议在下面粘贴 GitHub token；输入时不会显示。"
  echo "使用 token 时会绕开 git push，直接通过 GitHub API 只更新 outputs 网页文件。"
  echo "这不会合并远端旧程序，也不会覆盖整个仓库。"
  echo "不想输入 token，直接按回车跳过。"
  printf "GitHub token: "
  stty -echo
  read GITHUB_TOKEN
  stty echo
  echo
  if [ -n "$GITHUB_TOKEN" ]; then
    export GITHUB_TOKEN
    if python3 work/scripts/publish_github_pages.py --commit --push --token-env GITHUB_TOKEN; then
      echo
      echo "固定访问链接："
      echo "https://alexsheng666-bit.github.io/codex-A/outputs/stock_report.html"
    else
      echo
      echo "使用 token 发布仍未完成。请检查 token 是否有 repo / Contents 写入权限，以及网络是否可访问 github.com。"
    fi
    unset GITHUB_TOKEN
  else
    echo "已跳过 token 发布。"
  fi
fi
echo
echo "完成。按回车关闭窗口。"
read
