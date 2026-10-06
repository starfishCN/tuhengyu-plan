"""Server-side image preparation for the beginner install flow.

The user never handles Docker archives. A maintainer may configure one HTTPS
bundle URLs through IMAGE_BUNDLE_URLS; the panel tries them in order, imports the
first successful archive on the server, then verifies both required image tags.
"""
from __future__ import annotations
import os
import shlex
from pathlib import Path

ASTRBOT_IMAGE = "soulter/astrbot:latest"
SNOWLUMA_IMAGE = "motricseven7/snowluma:latest"
BUNDLE_DIR = Path(os.environ.get("IMAGE_BUNDLE_DIR", "/var/lib/tuhengyu/images"))
BUNDLE_URLS = tuple(
    value.strip()
    for value in os.environ.get("IMAGE_BUNDLE_URLS", os.environ.get("IMAGE_BUNDLE_URL", "")).split(",")
    if value.strip()
)
def image_prepare_cmds() -> list[str]:
    bundle_dir = shlex.quote(str(BUNDLE_DIR))
    bundle = shlex.quote(str(BUNDLE_DIR / "tuhengyu-images.tar"))
    urls = " ".join(shlex.quote(url) for url in BUNDLE_URLS) or "''"
    return [
        "command -v docker >/dev/null 2>&1 || { echo 'Docker 尚未安装'; exit 20; }",
        f"docker image inspect {ASTRBOT_IMAGE} >/dev/null 2>&1 && docker image inspect {SNOWLUMA_IMAGE} >/dev/null 2>&1 || "
        f"{{ found=0; for url in {urls}; do "
        f"echo '正在准备组件，请保持页面打开'; mkdir -p {bundle_dir}; "
        f"if curl -fL --retry 2 --connect-timeout 15 --max-time 3600 \"$url\" -o {bundle} && "
        f"test -s {bundle} && docker load -i {bundle}; then found=1; break; "
        f"else echo \"镜像包地址失败，正在切换备用地址\"; fi; done; "
        f"if test \"$found\" != 1; then echo '维护者镜像包地址均不可用，继续使用自动镜像线路'; fi; }}",
        f"docker image inspect {ASTRBOT_IMAGE} >/dev/null 2>&1 || {{ echo 'AstrBot 镜像未就绪'; exit 21; }}",
        f"docker image inspect {SNOWLUMA_IMAGE} >/dev/null 2>&1 || {{ echo 'SnowLuma 镜像未就绪'; exit 22; }}",
        "echo '组件镜像已准备完成'",
    ]
def bundle_configured() -> bool:
    return bool(BUNDLE_URLS)
