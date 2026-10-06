"""读取各组件入口与初始凭据（2026-10-01）。

背景：小白装完面板后，找不到 AstrBot / SnowLuma / noVNC 的初始密码。
实测确认三个来源：

  - noVNC     : 容器环境变量 VNC_PASSWD（部署时写入，**稳定**）
  - AstrBot   : /AstrBot/data/cmd_config.json 的 dashboard.password（初始密码）；旧版本回退启动日志
  - SnowLuma  : 启动日志 "initial credentials: user=admin password=xxx"
                （改密后失效；**未改密时重启会重新生成**）

⚠️ 日志里的都是「初始值」。用户一旦改密，这里无法反映真实密码。
页面必须明确提示这一点，不能让人误以为这是「当前密码」。
"""
from core.runner import run_capture

# (key, 显示名, 内部端口, 取密码的命令, 说明)
PROBES = [
    (
        "novnc",
        "远程桌面 noVNC",
        6081,
        "docker inspect snowluma "
        "--format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null "
        "| grep '^VNC_PASSWD=' | cut -d= -f2- | tail -n 1",
        "来自容器环境变量，部署时写入，最可靠",
    ),
    (
        "astrbot",
        "AstrBot 控制台",
        6185,
        "value=$(docker exec astrbot awk -F '\"' '/password/ {print $4; exit}' /AstrBot/data/cmd_config.json 2>/dev/null); "
        "if test -n \"$value\"; then printf '%s\\n' \"$value\"; else "
        "docker logs astrbot 2>&1 | grep -E 'Initial password' | tail -n 1 "
        "| sed -E 's/.*Initial password: *//' | tr -d '\\r'; fi",
        "优先读取配置中的初始密码；旧版本回退启动日志。改密后此处可能是旧值",
    ),
    (
        "snowluma",
        "SnowLuma 控制台",
        5099,
        "docker logs snowluma 2>&1 "
        "| grep -E 'initial credentials' | tail -n 1 "
        "| sed -E 's/.*password=//' | tr -d '\\r'",
        "来自启动日志；改密后失效，未改密时重启会换新的",
    ),
]

# 固定入口（非密码）
PORTS = [
    ("部署面板", 8080, "就是当前这个页面"),
    ("远程桌面 noVNC", 6081, "扫码登录 QQ 用"),
    ("SnowLuma 控制台", 5099, ""),
    ("AstrBot 控制台", 6185, ""),
    ("OneBot 通信口", 6199, "⚠️ 绝对不要映射到公网"),
]


async def gather() -> list:
    """逐个执行探测命令，返回结果列表。"""
    out = []
    for key, name, port, cmd, note in PROBES:
        code, raw = await run_capture(cmd)
        value = raw.strip().splitlines()[-1].strip() if raw.strip() else ""
        username = ""
        if key == "astrbot":
            _, user_raw = await run_capture(
                "docker exec astrbot awk -F '\"' '/username/ {print $4; exit}' "
                "/AstrBot/data/cmd_config.json 2>/dev/null"
            )
            username = user_raw.strip().splitlines()[-1].strip() if user_raw.strip() else ""
        elif key == "snowluma":
            username = "admin"
        out.append(
            {
                "key": key,
                "name": name,
                "port": port,
                "ok": bool(value),
                "value": value,
                "username": username,
                "note": note,
            }
        )
    return out
