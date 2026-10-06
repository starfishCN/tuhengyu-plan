"""Server-side image preparation for the beginner install flow.

The user never handles Docker archives. A maintainer may configure one HTTPS
bundle URL through IMAGE_BUNDLE_URL; the panel downloads and imports it on the
server, then verifies both required image tags.
"""
from __future__ import annotations
import os
import shlex
from pathlib import Path

ASTRBOT_IMAGE = "soulter/astrbot:latest"
SNOWLUMA_IMAGE = "motricseven7/snowluma:latest"
BUNDLE_DIR = Path(os.environ.get("IMAGE_BUNDLE_DIR", "/var/lib/tuhengyu/images"))
BUNDLE_URL = os.environ.get("IMAGE_BUNDLE_URL", "").strip()

def image_prepare_cmds() -> list[str]:
    url = shlex.quote(BUNDLE_URL)
    bundle = shlex.quote(str(BUNDLE_DIR / "tuhengyu-images.tar"))
    return [
        "command -v docker >/dev/null 2>&1 || { echo 'Docker 尚未安装'; exit 20; }",
        f"docker image inspect {ASTRBOT_IMAGE} >/dev/null 2>&1 && docker image inspect {SNOWLUMA_IMAGE} >/dev/null 2>&1 || "
        f"{{ if test -n {url}; then mkdir -p {shlex.quote(str(BUNDLE_DIR))}; "
        f"echo '正在准备组件，请保持页面打开'; "
        f"curl -fL --retry 3 --connect-timeout 15 --max-time 3600 {url} -o {bundle}; "
        f"test -s {bundle}; docker load -i {bundle}; "
        f"else echo '未配置维护者镜像包，继续使用自动镜像线路'; fi; }}",
        f"docker image inspect {ASTRBOT_IMAGE} >/dev/null 2>&1 || {{ echo 'AstrBot 镜像未就绪'; exit 21; }}",
        f"docker image inspect {SNOWLUMA_IMAGE} >/dev/null 2>&1 || {{ echo 'SnowLuma 镜像未就绪'; exit 22; }}",
        "echo '组件镜像已准备完成'",
    ]

def bundle_configured() -> bool:
    return bool(BUNDLE_URL)
