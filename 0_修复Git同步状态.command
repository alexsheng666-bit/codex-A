#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "正在检查 Git 同步状态..."
echo

if [ -d "$(git rev-parse --git-path rebase-merge 2>/dev/null)" ] || [ -d "$(git rev-parse --git-path rebase-apply 2>/dev/null)" ]; then
  echo "发现 Git 正在同步/变基中途，正在安全取消本次同步..."
  git rebase --abort
  echo
  echo "已恢复到同步前状态。"
else
  echo "没有发现 Git rebase 中途状态。"
fi

echo
echo "当前 Git 状态："
git status --short
echo
echo "完成。请再双击 7_发布到GitHub Pages.command。"
echo "按回车关闭窗口。"
read
