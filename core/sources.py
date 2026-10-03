"""镜像源 / 加速源：候选列表 + 测速 + 自动选最优。

⚠️ 可用性声明（重要）：
  下面列表来自公开常见列表，**未逐一实测**。国内公共 Docker 镜像加速在
  2024 年 6 月前后曾大面积停服，列表里可能有已失效项。
  所以本模块的定位是"给候选、让实测决定"，不是"保证可用"。
  以面板每次测速的结果为准；失效的源请在列表里删掉或补上新源。
"""
import asyncio
import time

import httpx

# ---------- 候选：Docker 镜像加速 ----------
# 2026-10-03 实测（探测 /v2/，正常 registry 应回 401 鉴权挑战或 200）：
#   DaoCloud   401 / 212ms  可用
#   dockerproxy 200 / 2985ms 可用（慢）
#   南京大学   403           探测有效但 /v2/ 被拒
#   1panel     403           同上
#   中科大 / 网易 / rainbond  不可达——已移除
DOCKER_MIRRORS = [
    {"name": "DaoCloud", "url": "https://docker.m.daocloud.io"},
    {"name": "dockerproxy", "url": "https://dockerproxy.com"},
    {"name": "南京大学", "url": "https://docker.nju.edu.cn"},
    {"name": "1panel", "url": "https://docker.1panel.live"},
    {"name": "阿里云（需填个人地址）", "url": ""},
]

# ---------- 候选：GitHub 加速 / 代理 ----------
# 用 SnowLuma 官方 install.sh 实际会尝试的那几个，测速结果才有参考价值。
# 注意：③ 安装 SnowLuma 已改为「内置脚本」，不依赖这些代理；本列表仅作备用/诊断。
GITHUB_PROXIES = [
    {"name": "ghfast.top", "prefix": "https://ghfast.top/"},
    {"name": "gh-proxy.com", "prefix": "https://gh-proxy.com/"},
    {"name": "gh.llkk.cc", "prefix": "https://gh.llkk.cc/"},
]

# ---------- 测速目标 ----------
DOCKER_PROBE = "/v2/"
GITHUB_PROBE = "https://raw.githubusercontent.com/SnowLuma/SnowLuma.Docker.Framework/main/install.sh"


def docker_mirror_url(item: dict) -> str:
    return item["url"].rstrip("/") + DOCKER_PROBE


def github_proxy_url_of(item: dict) -> str:
    target = GITHUB_PROBE.replace("https://", "")
    return item["prefix"] + target


async def _probe(url: str, timeout: float = 6.0) -> dict:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            r = await c.get(url)
        ms = round((time.perf_counter() - t0) * 1000)
        # 判定「可用」：正常 registry 对 /v2/ 回 401（鉴权挑战）或 2xx/3xx。
        # 403 是被拒/被墙，不能算可用——此前用 `<500` 会把 403 误判为可用。
        sc = r.status_code
        ok = (200 <= sc < 400) or sc == 401
        return {"ok": ok, "ms": ms, "status": sc}
    except Exception as e:
        return {"ok": False, "ms": None, "err": type(e).__name__}


async def test_all(items, url_of, timeout: float = 6.0) -> list:
    """并发测所有候选，返回 [{**item, 'result': {...}}]。"""

    async def one(it):
        return {**it, "result": await _probe(url_of(it), timeout)}

    return list(await asyncio.gather(*[one(it) for it in items]))


def pick_best(results: list):
    """选延迟最低的可用项；全不可用返回 None。"""
    ok = [r for r in results if r["result"]["ok"] and r["result"]["ms"] is not None]
    if not ok:
        return None
    return min(ok, key=lambda r: r["result"]["ms"])