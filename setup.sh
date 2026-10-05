#!/usr/bin/env bash
# 图恒宇计划 · 部署面板 —— 一键安装脚本
#
# 使用者在自己买的 Linux VPS 上执行本脚本，面板装好后浏览器访问
# http://<VPS_IP>:8080 即可看到部署面板。
#
# 仓库源策略：优先 Gitee（国内可直连），失败自动回退 GitHub。
#
# 密码策略（2026-10-03 改）：
#   初始密码在**本机随机生成**，只打印一次，不写进仓库。
#   首次登录会强制改密，改完存在面板目录的 .panel_auth.json 里。
set -euo pipefail

GITEE_URL="https://gitee.com/starfishCN/tuhengyu-plan.git"
GITHUB_URL="https://github.com/starfishCN/tuhengyu-plan.git"
INSTALL_DIR="${TUHENGYU_DIR:-/opt/tuhengyu-panel}"

echo "[图恒宇] 安装到 ${INSTALL_DIR}"

if [ "$(id -u)" -ne 0 ]; then
  echo "!! 面板需要 root 权限（要操作 Docker）。请用 sudo 运行。" >&2
  exit 1
fi

# ---------- 基础工具自动补齐 ----------
# 面向最小化 VPS：缺工具时自动安装，用户无需先查命令。
need_cmds=()
for _c in python3 git curl ca-certificates; do
  command -v "${_c}" >/dev/null 2>&1 || need_cmds+=("${_c}")
done
if [ "${#need_cmds[@]}" -gt 0 ]; then
  echo "[图恒宇] 缺少基础工具：${need_cmds[*]}，尝试自动安装"
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y python3 git curl ca-certificates
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3 git curl ca-certificates
  elif command -v yum >/dev/null 2>&1; then
    yum install -y python3 git curl ca-certificates
  else
    echo "!! 找不到 apt、dnf 或 yum，无法自动安装基础工具：${need_cmds[*]}" >&2
    exit 1
  fi
fi
command -v python3 >/dev/null 2>&1 || { echo "!! python3 自动安装失败。" >&2; exit 1; }
command -v git >/dev/null 2>&1 || { echo "!! git 自动安装失败。" >&2; exit 1; }

# 就地更新
if [ -d "${INSTALL_DIR}/.git" ]; then
  echo "[图恒宇] 目录已存在，尝试更新"
  git -C "${INSTALL_DIR}" pull --ff-only
else
  # 绝不删除非本项目目录。源码先进入临时目录，成功后才放入目标目录。
  if [ -e "${INSTALL_DIR}" ]; then
    if [ -n "$(find "${INSTALL_DIR}" -mindepth 1 -print -quit 2>/dev/null)" ]; then
      echo "!! 目标目录已存在且不是图恒宇计划仓库：${INSTALL_DIR}" >&2
      echo "!! 为保护现有文件，安装已停止。请备份后改用 TUHENGYU_DIR 指定空目录。" >&2
      exit 1
    fi
    rmdir "${INSTALL_DIR}"
  fi
  CLONE_DIR="${INSTALL_DIR}.download.$$"
  rm -rf "${CLONE_DIR}"
  ok=0
  for url in "${GITEE_URL}" "${GITHUB_URL}"; do
    echo "[图恒宇] 拉取源码：${url}"
    rm -rf "${CLONE_DIR}"
    if git clone --depth 1 "${url}" "${CLONE_DIR}"; then
      mv "${CLONE_DIR}" "${INSTALL_DIR}"
      ok=1
      break
    fi
    echo "[图恒宇] 该源不可用，保留目标目录不动，尝试下一个"
  done
  rm -rf "${CLONE_DIR}"
  [ "${ok}" -eq 1 ] || { echo "!! 所有源码源均不可用，请检查网络。" >&2; exit 1; }
fi

cd "${INSTALL_DIR}"

# ---------- 虚拟环境 ----------
# 有些发行版的最小化镜像不带 python3-venv（ensurepip 缺失），
# 直接 `python3 -m venv` 会报：
#   The virtual environment was not created successfully because
#   ensurepip is not available.
# 这里先试创建，失败则按需装 python3-venv 再重试。
PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if ! python3 -m venv .venv >/dev/null 2>&1; then
  echo "[图恒宇] venv 创建失败（缺 ensurepip），尝试安装 python3-venv"
  rm -rf .venv
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y || true
    apt-get install -y "python3-venv" "python3.${PYVER#*.}-venv" \
      || apt-get install -y python3-venv \
      || echo "[图恒宇] apt 安装 python3-venv 失败，继续尝试直接建 venv"
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3-virtualenv python3-pip || true
  elif command -v yum >/dev/null 2>&1; then
    yum install -y python3-virtualenv python3-pip || true
  fi
  python3 -m venv .venv || {
    echo "!! 虚拟环境仍创建失败。请手动安装 python3-venv（或 python3.${PYVER#*.}-venv）后重跑本脚本。" >&2
    exit 1
  }
fi
# ---------- 依赖安装 ----------
# 有些云机器对 PyPI 没有国际出口（报 Errno 101 Network is unreachable）。
# 直连失败时自动换国内镜像重试。
PIP=./.venv/bin/pip
pip_try() {
  "$PIP" install "$@" && return 0
  for _m in https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple/ https://pypi.mirrors.ustc.edu.cn/simple; do
    echo "[图恒宇] 直连 PyPI 失败，改用镜像：${_m}"
    "$PIP" install -i "${_m}" "$@" && return 0
  done
  echo "!! 依赖安装失败。可手动指定镜像后重跑，例如：" >&2
  echo "   ${PIP} install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt" >&2
  return 1
}
pip_try -U pip --timeout 20 --retries 1
pip_try -r requirements.txt --timeout 20 --retries 1

# ---------- 初始密码 ----------
# 不想用随机的，照下面这行自行指定：
#   PANEL_PASS='你的密码' bash setup.sh
PANEL_PASS_VALUE="${PANEL_PASS:-}"
if [ -z "${PANEL_PASS_VALUE}" ]; then
  PANEL_PASS_VALUE="$(head -c 64 /dev/urandom | tr -dc 'A-Za-z0-9' | head -c 16)"
fi

# ---------- 安装 systemd 服务 ----------
# 面板能执行系统命令（装 Docker、改 daemon.json），**必须**带登录认证。
# 认证靠 PANEL_USER / PANEL_PASS 两个环境变量传入；仓库里的
# deploy/tuhengyu-panel.service 里是占位符 __PANEL_PASS__，
# 由本脚本替换成上面生成的随机值。
SERVICE=/etc/systemd/system/tuhengyu-panel.service
if [ -f "${SERVICE}" ]; then
  systemctl restart tuhengyu-panel
  CURRENT_PASS="$(sed -n 's/^Environment=PANEL_PASS=//p' "${SERVICE}" | head -n 1)"
  echo "[图恒宇] systemd 服务已存在，已重启（密码沿用原有配置）"
else
  cp "${INSTALL_DIR}/deploy/tuhengyu-panel.service" "${SERVICE}"
  sed -i "s|__PANEL_PASS__|${PANEL_PASS_VALUE}|" "${SERVICE}"
  systemctl daemon-reload
  systemctl enable --now tuhengyu-panel
  CURRENT_PASS="${PANEL_PASS_VALUE}"
  echo "[图恒宇] systemd 服务已安装并启动"
fi

echo "[图恒宇] 安装完成。"
echo "[图恒宇]   面板地址：http://<你的服务器IP>:8080"
echo "[图恒宇]   账号：admin"
echo "[图恒宇]   初始密码：${CURRENT_PASS}"
echo "[图恒宇]   ⚠️ 这是**临时密码**，首次登录会强制你改成自己的。"
echo "[图恒宇]   查看状态：systemctl status tuhengyu-panel"
