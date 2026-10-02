#!/bin/sh
# 设备同步辅助脚本（配合仓库根 WORKFLOW.md）
# 用法：
#   sh scripts/sync.sh start          # 开工前：拉取，并显示其他设备是否推过新提交
#   sh scripts/sync.sh done "说明"    # 收工后：提交并推送
cd "$(dirname "$0")/.." || exit 1

case "${1:-}" in
  start)
    git fetch origin || exit 1
    echo "--- 其他设备的新提交（空 = 无） ---"
    git log --oneline HEAD..origin/main
    git pull --rebase origin main || exit 1
    echo "已同步到最新。"
    ;;
  done)
    msg="${2:-update}"
    git add -A || exit 1
    if git diff --cached --quiet; then
      echo "无改动可提交。"
    else
      git commit -m "$msg" || exit 1
    fi
    git push origin main || exit 1
    echo "已推送。"
    ;;
  *)
    echo "用法: sh scripts/sync.sh start | done \"提交说明\""
    exit 2
    ;;
esac