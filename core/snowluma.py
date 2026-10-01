"""③ 安装 SnowLuma（调用官方脚本）。

来源：https://github.com/SnowLuma/SnowLuma.Docker.Framework （Alpha）
官方安装：curl -fsSL .../install.sh | bash
非交互：加 --mode docker --yes

GitHub raw 国内直连不通，因此本模块接受一个「加速前缀」——
由面板「网络源」区测速选出的最优 GitHub 代理传进来。
"""

BASE_URL = "https://raw.githubusercontent.com/SnowLuma/SnowLuma.Docker.Framework/main/install.sh"


def snowluma_cmds(proxy_prefix: str = "") -> list:
    if proxy_prefix:
        url = proxy_prefix.rstrip("/") + "/" + BASE_URL.replace("https://", "")
    else:
        url = BASE_URL
    return [
        f"curl -fsSL {url} | bash -s -- --mode docker --yes",
        "docker ps --filter name=snowluma",
    ]