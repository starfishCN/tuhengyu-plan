"""④ 安装 AstrBot（官方 Docker 镜像）。

来源：https://docs.astrbot.app/deploy/astrbot/docker.html
镜像：soulter/astrbot:latest
国内加速：m.daocloud.io/docker.io/soulter/astrbot:latest
端口：6185（WebUI）、6199

同时**预置配套插件**（PLUGIN_STAGE_CMDS）：在容器创建之前把插件放进
./data/plugins/，容器一起来就能看到 —— 省掉「装完还要手动拷插件」一步。
（AstrBot 插件市场在无国际出口的机器上不可用，所以这一步不能靠市场。）
"""

from .plugin import PLUGIN_STAGE_CMDS

ASTRBOT_IMAGE = "soulter/astrbot:latest"

ASTRBOT_CMDS = PLUGIN_STAGE_CMDS + [
    (
        "docker run -d --name astrbot --restart always "
        "-p 6185:6185 -p 6199:6199 "
        "-v $PWD/data:/AstrBot/data "
        "-v /etc/localtime:/etc/localtime:ro "
        "-v /etc/timezone:/etc/timezone:ro "
        f"{ASTRBOT_IMAGE}"
    ),
    "docker ps --filter name=astrbot",
]
