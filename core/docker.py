"""② 安装 Docker CE（走国内镜像源，缺才装）＋ 应用镜像加速。

来源：阿里云 Docker CE 镜像 https://mirrors.aliyun.com/docker-ce/linux/ubuntu
实测（2026-10-01，国内 VPS）：get.docker.com / download.docker.com 均不可达（超时），
故不用官方便捷脚本，改走 apt + 国内镜像源。
"""
import json

MIRROR = "https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu"

DOCKER_CMDS = [
    # 已有 Docker 时只校验并启动，避免重复改动系统软件源和软件包。
    "if command -v docker >/dev/null 2>&1; then echo 'Docker 已安装，跳过安装'; else apt-get update && apt-get install -y ca-certificates curl gnupg && install -m 0755 -d /etc/apt/keyrings && curl -fsSL " + MIRROR + "/gpg -o /etc/apt/keyrings/docker.asc && chmod a+r /etc/apt/keyrings/docker.asc && echo \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] " + MIRROR + " $(. /etc/os-release && echo $VERSION_CODENAME) stable\" > /etc/apt/sources.list.d/docker.list && apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; fi",
    "systemctl enable --now docker 2>/dev/null || service docker start 2>/dev/null || true",
    "docker -v",
    "docker compose version",
]


def daemon_json_text(mirror_url: str) -> str:
    return json.dumps({"registry-mirrors": [mirror_url]}, indent=2, ensure_ascii=False)


def apply_mirror_cmds(mirror_url: str) -> list:
    """备份并合并 /etc/docker/daemon.json，然后重启 Docker。需 root。"""
    import shlex

    quoted = shlex.quote(mirror_url)
    write = (
        "mkdir -p /etc/docker && "
        "if [ -f /etc/docker/daemon.json ]; then "
        "cp -n /etc/docker/daemon.json /etc/docker/daemon.json.tuhengyu.bak; fi && "
        "python3 -c "
        + shlex.quote(
            "import json, pathlib, sys; "
            "p=pathlib.Path('/etc/docker/daemon.json'); "
            "data=json.loads(p.read_text()) if p.exists() else {}; "
            "data['registry-mirrors']=[sys.argv[1]]; "
            "p.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\\n')"
        )
        + " "
        + quoted
        + " && (systemctl restart docker 2>/dev/null || service docker restart 2>/dev/null)"
    )
    return [write, "cat /etc/docker/daemon.json"]