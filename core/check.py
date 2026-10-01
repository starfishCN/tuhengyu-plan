"""① 环境体检：只读，不装任何东西。"""

CHECK_CMDS = [
    "cat /etc/os-release | head -n 2",
    "uname -m",
    "id -u",
    "docker -v 2>/dev/null || echo 'docker: 未安装'",
    "docker compose version 2>/dev/null || echo 'docker compose: 未安装'",
    "ss -tlnp 2>/dev/null | head -n 20 || echo 'ss 不可用'",
]
