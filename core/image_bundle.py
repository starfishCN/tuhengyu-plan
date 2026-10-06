"""Prepare required images on the user's server.

The beginner flow first reuses local images, then tries Docker Hub directly
and a list of public pull-through prefixes. Maintainer-hosted archives remain
an optional later fallback.
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
    for value in os.environ.get(
        "IMAGE_BUNDLE_URLS", os.environ.get("IMAGE_BUNDLE_URL", "")
    ).split(",")
    if value.strip()
)
DEFAULT_PULL_PROXIES = (
    "dockerpull.org",
    "docker.1ms.run",
    "docker.xuanyuan.me",
    "docker.m.daocloud.io",
    "hub.rat.dev",
    "docker.awsl9527.cn",
)
PULL_PROXIES = tuple(
    value.strip().rstrip("/")
    for value in os.environ.get(
        "DOCKER_PULL_PROXIES", ",".join(DEFAULT_PULL_PROXIES)
    ).split(",")
    if value.strip()
)


def image_prepare_cmds() -> list[str]:
    bundle_dir = shlex.quote(str(BUNDLE_DIR))
    urls = " ".join(shlex.quote(url) for url in BUNDLE_URLS) or "''"
    proxies = " ".join(shlex.quote(proxy) for proxy in PULL_PROXIES) or "''"
    images = " ".join(
        shlex.quote(image) for image in (ASTRBOT_IMAGE, SNOWLUMA_IMAGE)
    )
    return [
        "command -v docker >/dev/null 2>&1 || { echo 'Docker 尚未安装'; exit 20; }",
        f"{{ found=0; for url in {urls}; do "
        f"echo '正在尝试维护者镜像包'; mkdir -p {bundle_dir}; "
        f"name=$(printf '%s' \"$url\" | sha256sum | cut -c1-12); "
        f"target={bundle_dir}/bundle-$name.tar.gz; "
        f"if curl -fL --retry 2 --connect-timeout 15 --max-time 3600 \"$url\" -o \"$target\" && "
        f"test -s \"$target\" && gzip -t \"$target\" && gzip -dc \"$target\" | docker load; then "
        f"found=1; break; else echo '镜像包地址失败，继续尝试下一条'; fi; done; "
        f"if test \"$found\" != 1; then echo '镜像包不可用，改用自动镜像线路'; fi; }}",
        f"for image in {images}; do "
        "if docker image inspect \"$image\" >/dev/null 2>&1; then "
        "echo \"镜像已存在：$image\"; continue; fi; "
        "pulled=0; for source in '' " + proxies + "; do "
        "if test -n \"$source\"; then candidate=\"$source/$image\"; else candidate=\"$image\"; fi; "
        "echo \"正在尝试镜像线路：$candidate\"; "
        "if timeout 900 docker pull \"$candidate\"; then "
        "if test \"$candidate\" != \"$image\"; then docker tag \"$candidate\" \"$image\" && docker rmi \"$candidate\" >/dev/null 2>&1 || true; fi; "
        "if docker image inspect \"$image\" >/dev/null 2>&1; then pulled=1; echo \"镜像准备完成：$image\"; break; fi; fi; "
        "echo '当前线路不可用，切换下一条'; done; "
        "if test \"$pulled\" != 1; then echo \"镜像获取失败：$image\"; exit 23; fi; done",
        f"docker image inspect {shlex.quote(ASTRBOT_IMAGE)} >/dev/null 2>&1 || {{ echo 'AstrBot 镜像未就绪'; exit 21; }}",
        f"docker image inspect {shlex.quote(SNOWLUMA_IMAGE)} >/dev/null 2>&1 || {{ echo 'SnowLuma 镜像未就绪'; exit 22; }}",
        "echo '组件镜像已准备完成'",
    ]


def bundle_configured() -> bool:
    return bool(BUNDLE_URLS)
