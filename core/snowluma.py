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
        run = f"bash {VENDOR_SCRIPT} --mode docker --yes"
    else:
        if proxy_prefix:
            url = proxy_prefix.rstrip("/") + "/" + BASE_URL.replace("https://", "")
        else:
            url = BASE_URL
        fetch = f"curl -fsSL {url} -o /tmp/snowluma_install.sh"
        run = "bash /tmp/snowluma_install.sh --mode docker --yes"
    return [fetch, run, "docker ps --filter name=snowluma"]