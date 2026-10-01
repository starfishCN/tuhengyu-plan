"""④ 安装 AstrBot（官方 Docker 镜像）。

来源：https://docs.astrbot.app/deploy/astrbot/docker.html
镜像：soulter/astrbot:latest
国内加速：m.daocloud.io/docker.io/soulter/astrbot:latest
端口：6185（WebUI）、6199
"""

ASTRBOT_IMAGE = "soulter/astrbot:latest"

ASTRBOT_CMDS = [
    "mkdir -p ./data",
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
