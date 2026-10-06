"""Offline Docker image package upload/import helpers."""
from __future__ import annotations

import os
import shlex
import time
from pathlib import Path

_PANEL_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = _PANEL_DIR / ".uploads"
MAX_PACKAGE_BYTES = 30 * 1024 * 1024 * 1024
ALLOWED_SUFFIXES = (".tar", ".tar.gz", ".tgz")
IMAGE_OPTIONS = {
    "SnowLuma": "motricseven7/snowluma:latest",
    "AstrBot": "soulter/astrbot:latest",
}
DEFAULT_IMAGE = IMAGE_OPTIONS["SnowLuma"]


def safe_upload_name(name: str) -> str:
    base = Path(name or "image.tar").name
    if not base.lower().endswith(ALLOWED_SUFFIXES):
        raise ValueError("只接受 .tar、.tar.gz 或 .tgz Docker 镜像包")
    if base.startswith(".") or base in {".", ".."}:
        raise ValueError("文件名无效")
    return base


def ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    return UPLOAD_DIR


def unique_upload_path(filename: str) -> Path:
    target = ensure_upload_dir() / filename
    if not target.exists():
        return target
    suffix = target.suffix
    stem = target.name[:-len(suffix)] if suffix else target.name
    counter = 2
    while True:
        candidate = target.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def import_cmds(package: Path, image: str = DEFAULT_IMAGE) -> list[str]:
    package_q = shlex.quote(str(package))
    image_q = shlex.quote(image)
    return [
        f"test -s {package_q}",
        f"docker load -i {package_q}",
        f"docker image inspect {image_q}",
        f"docker image inspect {image_q} --format='镜像已就绪：{{{{.Id}}}}'",
    ]


def list_packages() -> list[Path]:
    if not UPLOAD_DIR.is_dir():
        return []
    return sorted(
        (p for p in UPLOAD_DIR.iterdir() if p.is_file() and p.name.lower().endswith(ALLOWED_SUFFIXES)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
