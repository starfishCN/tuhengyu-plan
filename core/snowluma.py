"""③ 安装 SnowLuma（优先用面板内置的官方脚本）。

来源：https://github.com/SnowLuma/SnowLuma.Docker.Framework （Alpha）

为什么内置：
  2026-10-01 实测，目标国内 VPS 对 GitHub 全系（raw / api / codeload）不可达，
  所有公共加速站（ghfast.top / gh-proxy.com / gh.llkk.cc / jsdelivr）也全部超时。
  但官方 install.sh 的 docker 模式**不依赖 GitHub**（compose 内容是脚本内联生成的），
  因此把脚本本体放进面板 vendor/ 一起分发，即可完全离线安装。

  仅在 vendor 脚本缺失时才回退到网络拉取（走面板选出的加速前缀）。
"""
import os

BASE_URL = (
    "https://raw.githubusercontent.com/"
    "SnowLuma/SnowLuma.Docker.Framework/main/install.sh"
)

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
VENDOR_SCRIPT = os.path.join(
    os.path.dirname(_CORE_DIR), "vendor", "snowluma_install.sh"
)


def snowluma_cmds(proxy_prefix: str = "") -> list:
    if os.path.isfile(VENDOR_SCRIPT):
        fetch = f"echo '使用内置安装脚本'; ls -l {VENDOR_SCRIPT}"
        install = f"bash {VENDOR_SCRIPT} --mode docker --yes"
    else:
        if proxy_prefix:
            url = proxy_prefix.rstrip("/") + "/" + BASE_URL.replace("https://", "")
        else:
            url = BASE_URL
        fetch = f"curl -fsSL {url} -o /tmp/snowluma_install.sh"
        install = "bash /tmp/snowluma_install.sh --mode docker --yes"
    run = (
        "if docker inspect -f '{{.State.Status}}' snowluma 2>/dev/null | grep -qx running; "
        "then echo 'SnowLuma 容器已运行，跳过重复安装'; "
        f"else {install}; fi"
    )
    config_file = os.path.join(os.path.dirname(_CORE_DIR), "vendor", "snowluma_ws_config.js")
    configure = [
        f"test -f {config_file} || echo 'WS 配置文件不存在，跳过自动连接配置'",
        f"test -f {config_file} && docker cp {config_file} snowluma:/tmp/snowluma_ws_config.js || true",
        "docker exec snowluma test -f /tmp/snowluma_ws_config.js && docker exec snowluma node /tmp/snowluma_ws_config.js || echo 'WS 自动配置失败，稍后可在 SnowLuma 面板中手动配置'",
        "docker restart snowluma >/dev/null 2>&1 || echo 'SnowLuma 重启跳过，容器可能正在启动'",

    ]
    return [
        fetch,
        run,
        *configure,
        "docker inspect -f '{{.State.Status}}' snowluma 2>/dev/null | grep -qx running || { echo 'SnowLuma 容器未运行'; exit 24; }",
        "docker ps --filter name=snowluma",
    ]