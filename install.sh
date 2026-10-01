#!/usr/bin/env bash
# 图恒宇计划 · 部署面板 —— 一键安装脚本
#
# 使用者在自己买的 Linux VPS 上执行本脚本，面板装好后浏览器访问
# http://<VPS_IP>:8080 即可看到部署面板。
#
# 仓库源策略：优先 Gitee（国内可直连），失败自动回退 GitHub。
set -euo pipefail

GITEE_URL="https://gitee.com/starfishCN/tuhengyu-plan.git"
GITHUB_URL="https://github.com/starfishCN/tuhengyu-plan.git"
INSTALL_DIR="${TUHENGYU_DIR:-/opt/tuhengyu-panel}"

echo "[图恒宇] 安装到 ${INSTALL_DIR}"

if [ "$(id -u)" -ne 0 ]; then
  echo "!! 面板需要 root 权限（要操作 Docker）。请用 sudo 运行。" >&2
  exit 1
fi

command -v python3 >/dev/null 2>&1 || { echo "!! 缺 python3，请先装。" >&2; exit 1; }
command -v git >/dev/null 2>&1 || { echo "!! 缺 git，请先装。" >&2; exit 1; }

# 就地更新
if [ -d "${INSTALL_DIR}/.git" ]; then
  echo "[图恒宇] 目录已存在，尝试更新"
  git -C "${INSTALL_DIR}" pull --ff-only
else
  # 先 Gitee，后 GitHub
  ok=0
  for url in "${GITEE_URL}" "${GITHUB_URL}"; do
    echo "[图恒宇] 拉取源码：${url}"
    if git clone --depth 1 "${url}" "${INSTALL_DIR}"; then
      ok=1; break
    fi
    echo "[图恒宇] 该源不可用，尝试下一个"
    rm -rf "${INSTALL_DIR}"
  done
  [ "${ok}" -eq 1 ] || { echo "!! 所有源码源均不可用，请检查网络。" >&2; exit 1; }
fi

cd "${INSTALL_DIR}"
python3 -m venv .venv
./.venv/bin/pip install -U pip
./.venv/bin/pip install -r requirements.txt

echo "[图恒宇] 安装完成。启动：${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/main.py"
