#!/usr/bin/env bash
# 图恒宇计划 · 新手入口引导脚本
# 作用：在最小化 VPS 上补齐下载工具，再获取正式 setup.sh。
set -u

REPO="starfishCN/tuhengyu-plan"
TARGET="/tmp/tuhengyu-setup.sh"

say() { echo "[图恒宇] $*"; }
fail() { echo "!! $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "请以 root 身份执行。"

install_tools() {
  command -v curl >/dev/null 2>&1 && return 0
  command -v wget >/dev/null 2>&1 && return 0
  say "缺少下载工具，尝试自动安装 curl。"
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y && apt-get install -y curl ca-certificates
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y curl ca-certificates
  elif command -v yum >/dev/null 2>&1; then
    yum install -y curl ca-certificates
  else
    return 1
  fi
}

fetch() {
  local url="$1" out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fL --connect-timeout 10 --max-time 60 --retry 1 "$url" -o "$out"
  elif command -v wget >/dev/null 2>&1; then
    wget -T 60 -O "$out" "$url"
  else
    return 1
  fi
}

install_tools || fail "无法自动安装 curl/wget。请换一台可访问软件源的服务器。"
rm -f "$TARGET"

# 顺序按国内可达性排列。每次下载后都检查内容，避免把错误页当脚本执行。
URLS=(
  "https://cdn.jsdelivr.net/gh/${REPO}@main/setup.sh"
  "https://raw.githubusercontent.com/${REPO}/main/setup.sh"
  "https://gitee.com/${REPO}/raw/main/setup.sh"
)
for url in "${URLS[@]}"; do
  say "尝试安装源：${url}"
  if fetch "$url" "$TARGET" && grep -q '^#!/usr/bin/env bash' "$TARGET" && grep -q '图恒宇' "$TARGET"; then
    chmod 700 "$TARGET"
    say "已取得正式安装脚本，开始安装。"
    exec bash "$TARGET"
  fi
  rm -f "$TARGET"
done

fail "所有安装源均不可用。请检查服务器网络，或换线路后重试。"
