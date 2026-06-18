#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "正在刷新数据并发布到固定 GitHub Pages 链接..."
echo

if [ -d "$(git rev-parse --git-path rebase-merge 2>/dev/null)" ] || [ -d "$(git rev-parse --git-path rebase-apply 2>/dev/null)" ]; then
  echo "检测到 Git 仍处于同步中途状态。"
  echo "请先双击 0_修复Git同步状态.command，完成后再运行本发布入口。"
  echo
  echo "按回车关闭窗口。"
  read
  exit 1
fi

echo "步骤 1/2：刷新行情、筛选、复盘和看板"
echo "如果网络较慢，下面会显示每个子步骤的进度。"
python3 -u work/scripts/refresh_dashboard_live.py
echo

echo "步骤 2/2：发布到 GitHub Pages"
if python3 work/scripts/publish_github_pages.py --commit --push --publish-cloud-source; then
  echo
  echo "已发布到固定访问链接："
  echo "https://alexsheng666-bit.github.io/codex-A/outputs/stock_report.html"
else
  echo
  echo "正常发布没有完成。常见原因："
  echo "1. 终端无法连接 github.com。"
  echo "2. 当前电脑还没有登录 GitHub。"
  echo "3. 仓库没有推送权限。"
  echo
  echo "如果普通 Git 推送失败，建议在下面粘贴 GitHub token；输入时不会显示。"
  echo "使用 token 时会绕开 git push，直接通过 GitHub API 更新网页和云端刷新程序。"
  echo "这不会覆盖整个仓库，只会更新本项目运行必需的文件。"
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
      echo "已发布到固定访问链接："
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
