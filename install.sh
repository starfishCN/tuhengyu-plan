#!/usr/bin/env bash
# 图恒宇计划 · 部署面板 —— 一键安装脚本（骨架）
#
# 使用者在自己买的 Linux VPS 上执行本脚本，面板装好后浏览器访问
# http://<VPS_IP>:8080 即可看到部署面板。
#
# ⚠️ 待定：仓库地址未定，先占位。定好后替换 REPO_URL 并放到仓库根目录。
set -euo pipefail

REPO_URL="https://github.com/starfishCN/tuhengyu-plan.git"
INSTALL_DIR="${TUHENGYU_DIR:-/opt/tuhengyu-panel}"

echo "[图恒宇] 安装到 ${INSTALL_DIR}"

if [ "$(id -u)" -ne 0 ]; then
  echo "!! 面板需要 root 权限（要操作 Docker）。请用 sudo 运行。" >&2
  exit 1
fi

command -v python3 >/dev/null 2>&1 || { echo "!! 缺 python3，请先装。" >&2; exit 1; }
command -v git >/dev/null 2>&1 || { echo "!! 缺 git，请先装。" >&2; exit 1; }

git clone --depth 1 "${REPO_URL}" "${INSTALL_DIR}" 2>/dev/null || {
  echo "[图恒宇] 目录已存在，尝试更新"; git -C "${INSTALL_DIR}" pull --ff-only
}

cd "${INSTALL_DIR}"
python3 -m venv .venv
./.venv/bin/pip install -U pip
./.venv/bin/pip install -r requirements.txt

echo "[图恒宇] 安装完成。启动：${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/main.py"
