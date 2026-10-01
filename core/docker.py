"""② 安装 Docker（缺才装）＋ 应用镜像加速。

来源：Docker 官方便捷脚本 https://get.docker.com
注意：国内网络直连可能慢/失败，请先用面板「网络源」区测速并选择镜像。
"""
import json

DOCKER_CMDS = [
    "curl -fsSL https://get.docker.com -o /tmp/get-docker.sh",
    "sh /tmp/get-docker.sh",
    "systemctl enable --now docker 2>/dev/null || service docker start 2>/dev/null || true",
    "docker -v",
]


def daemon_json_text(mirror_url: str) -> str:
    return json.dumps({"registry-mirrors": [mirror_url]}, indent=2, ensure_ascii=False)


def apply_mirror_cmds(mirror_url: str) -> list:
    """写入 /etc/docker/daemon.json 并重启 Docker。需 root。"""
    txt = daemon_json_text(mirror_url)
    write = (
        "mkdir -p /etc/docker && "
        "cat > /etc/docker/daemon.json <<'EOF'\n" + txt + "\nEOF\n"
        "systemctl restart docker 2>/dev/null || service docker restart 2>/dev/null || true"
    )
    return [write, "cat /etc/docker/daemon.json"]