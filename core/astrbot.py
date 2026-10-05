"""④ 安装 AstrBot（官方 Docker 镜像）。
来源：https://docs.astrbot.app/deploy/astrbot/docker.html
镜像：soulter/astrbot:latest
国内加速：m.daocloud.io/docker.io/soulter/astrbot:latest
端口：6185（WebUI）；6199 仅供 maim_bot 容器网络内部通信
同时**预置配套插件**（PLUGIN_STAGE_CMDS）：在容器创建之前把插件放进
./data/plugins/，容器一起来就能看到 —— 省掉「装完还要手动拷插件」一步。
（AstrBot 插件市场在无国际出口的机器上不可用，所以这一步不能靠市场。）
"""

from .plugin import PLUGIN_STAGE_CMDS
ASTRBOT_IMAGE = "soulter/astrbot:latest"
ASTRBOT_NETWORK = "maim_bot"
# 拉镜像：先直连，失败走 DaoCloud 前缀再重打标签（无国际出口机器用；
# 若面板已配 daemon.json 镜像加速，第一跳即可成功）。
PULL_CMDS = [
    f"docker image inspect {ASTRBOT_IMAGE} >/dev/null 2>&1 || "
    f"(docker pull {ASTRBOT_IMAGE} || "
    f"(docker pull m.daocloud.io/docker.io/{ASTRBOT_IMAGE} && "
    f"docker tag m.daocloud.io/docker.io/{ASTRBOT_IMAGE} {ASTRBOT_IMAGE}))",
]
ASTRBOT_CMDS = PLUGIN_STAGE_CMDS + PULL_CMDS + [
    f"docker network inspect {ASTRBOT_NETWORK} >/dev/null 2>&1 || docker network create {ASTRBOT_NETWORK}",
    "docker rm -f astrbot >/dev/null 2>&1 || true",
    (
        "docker run -d --name astrbot --restart always "
        f"--network {ASTRBOT_NETWORK} "
        "-p 6185:6185 "
        "-v $PWD/data:/AstrBot/data "

        "-v /etc/localtime:/etc/localtime:ro "
        "-v /etc/timezone:/etc/timezone:ro "
        f"{ASTRBOT_IMAGE}"
    ),
    "docker ps --filter name=astrbot",
]
