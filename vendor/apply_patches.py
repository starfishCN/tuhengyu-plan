"""对 SnowLuma 官方 install.sh 打本地适配补丁。

背景：官方脚本随面板 vendor/ 一起分发，但存在与新版 Docker 不兼容的判据，
直接使用会导致安装中止。本脚本记录补丁内容，便于官方脚本更新后重新打补丁。

用法：
    python3 apply_patches.py <install.sh 路径>

补丁清单
--------
[P1] is_snap_docker 误判（2026-10-01）
    原判据：docker info 2>/dev/null | grep -qi 'snap' && return 0
    问题：Docker 29.x 的 `docker info` 输出含 `io.containerd.snapshotter.v1`，
          其中 "snapshotter" 包含子串 "snap"，导致正版 apt 安装的 Docker CE
          被误判为 snap 版，脚本报「检测到 snap 版 Docker」并中止。
    修法：去掉该宽泛匹配，只保留 `command -v docker` 的 /snap/ 路径判断。
"""
import pathlib
import sys

PATCHES = [
    {
        "id": "P1",
        "old": "  docker info 2>/dev/null | grep -qi 'snap' && return 0",
        "new": (
            "  # [patched] 原判据 docker info | grep -qi 'snap' 会被 Docker 29.x 的\n"
            "  # io.containerd.snapshotter.v1 误匹配，改为只认 /snap/ 路径。"
        ),
    },
    {
        "id": "P2",
        "old": '  step "拉取镜像 ${IMAGE}"\n  local refs=(',
        "new": (
            '  step "拉取镜像 ${IMAGE}"\n'
            "  # [patched] 本地已有镜像时跳过：docker pull 总会访问 registry 查更新，\n"
            "  # 在无国际出口的机器上即便镜像已中转载入也会失败。\n"
            '  if docker image inspect "${IMAGE}" >/dev/null 2>&1; then\n'
            '    ok "镜像 ${IMAGE} 已存在，跳过拉取"\n'
            "    return 0\n"
            "  fi\n"
            "  local refs=("
        ),
    },
]


def main(path: str) -> int:
    p = pathlib.Path(path)
    if not p.is_file():
        print(f"找不到文件: {path}")
        return 1
    text = p.read_text(encoding="utf-8")
    applied = 0
    for patch in PATCHES:
        if patch["old"] not in text:
            if patch["new"] in text:
                print(f"[{patch['id']}] 已打过，跳过")
            else:
                print(f"[{patch['id']}] 未找到目标代码，跳过")
            continue
        text = text.replace(patch["old"], patch["new"], 1)
        applied += 1
        print(f"[{patch['id']}] 已应用")
    p.write_text(text, encoding="utf-8")
    print(f"完成，应用 {applied} 个补丁")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1]))