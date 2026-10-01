"""图恒宇计划 · 部署面板（NiceGUI）—— 骨架 v0.2

本版新增「网络源」区：镜像加速 / GitHub 加速的候选列表 + 并发测速 + 自动选优。
跑在目标 Linux VPS 上，需 root（或 docker 组）权限。

注意：NiceGUI / httpx 的 API 以你安装的版本为准。
"""
import asyncio
import base64
import os

from nicegui import app, ui
from fastapi.responses import Response as _Resp

from core.runner import run_stream_all
from core.check import CHECK_CMDS
from core.docker import DOCKER_CMDS, apply_mirror_cmds
from core.snowluma import snowluma_cmds
from core.astrbot import ASTRBOT_CMDS
from core import sources
from core import credentials

STATE = {"busy": False, "mirror": None, "proxy": None}
LOG = None


def _fmt(r: dict) -> str:
    res = r["result"]
    if res["ok"]:
        return f"{res['ms']} ms"
    return f"不可用（{res.get('err') or res.get('status')}）"


def _guard() -> bool:
    if STATE["busy"]:
        ui.notify("有任务正在执行，请等它结束。", type="warning")
        return False
    STATE["busy"] = True
    return True


async def _run(title: str, cmds: list):
    LOG.push(f"===== {title} =====")
    try:
        code = await run_stream_all(cmds, LOG.push)
        ui.notify(
            f"{title} {'完成' if code == 0 else f'失败（退出码 {code}）'}",
            type="positive" if code == 0 else "negative",
        )
    finally:
        STATE["busy"] = False
        LOG.push(f"===== {title} 结束 =====")


def _handler(title, cmds):
    async def _h():
        if not _guard():
            return
        await _run(title, cmds)

    return _h


def _dynamic_handler(title, cmds_fn):
    async def _h():
        if not _guard():
            return
        await _run(title, cmds_fn())

    return _h


def source_section():
    ui.markdown("#### 网络源（镜像加速 / GitHub 加速）")
    ui.markdown(
        "国内直连 docker / github 常常不通。点测速，面板会并发测所有候选，"
        "自动预选延迟最低的可用线路；**也可以手动点选**。\n\n"
        "⚠️ 候选来自公开列表，**未逐一实测**；国内公共 Docker 镜像曾大面积停服，"
        "**以每次测速结果为准**。失效项请在 `core/sources.py` 里增删。"
    )
    mirror_status = ui.label("镜像加速：未选（先测速，再点选）")
    proxy_status = ui.label("GitHub 加速：未选")

    # 可手动点选的单选组；测速后自动填选项并预选最优
    mirror_select = ui.radio({}, value=None)
    proxy_select = ui.radio({}, value=None)

    async def speedtest():
        if not _guard():
            return
        LOG.push("===== 源测速 =====")
        try:
            m, p = await asyncio.gather(
                sources.test_all(sources.DOCKER_MIRRORS, sources.docker_mirror_url),
                sources.test_all(sources.GITHUB_PROXIES, sources.github_proxy_url_of),
            )
            best_m, best_p = sources.pick_best(m), sources.pick_best(p)
            STATE["mirror"], STATE["proxy"] = best_m, best_p
            key = lambda r: (not r["result"]["ok"], r["result"]["ms"] or 9e9)

            mirror_select.options = {
                r["url"]: f"{r['name']} —— {_fmt(r)}" for r in sorted(m, key=key)
            }
            mirror_select.value = best_m["url"] if best_m else None
            mirror_select.update()

            proxy_select.options = {
                r["prefix"]: f"{r['name']} —— {_fmt(r)}" for r in sorted(p, key=key)
            }
            proxy_select.value = best_p["prefix"] if best_p else None
            proxy_select.update()

            mirror_status.text = f"镜像加速：{best_m['name'] if best_m else '无可用'}"
            proxy_status.text = f"GitHub 加速：{best_p['name'] if best_p else '无可用'}"
            ui.notify("测速完成，可手动改选")
        finally:
            STATE["busy"] = False
            LOG.push("===== 源测速 结束 =====")

    ui.button("一键测速并自动选优", on_click=speedtest)

    ui.label("↓ 点一下选中要用的镜像（测速后可改）")
    mirror_select
    proxy_select

    async def apply_mirror():
        url = mirror_select.value
        if not url:
            ui.notify("请先测速，并点选一个镜像源", type="warning")
            return
        if not _guard():
            return
        await _run("应用 Docker 镜像加速", apply_mirror_cmds(url))

    ui.button("应用选中的镜像加速（写 daemon.json 并重启 Docker）", on_click=apply_mirror)


def credential_section():
    ui.markdown(
        "装完之后，各家控制台的密码分散在**容器日志**和**环境变量**里，"
        "新手很难找到。点下面的按钮，面板替你读出来。\n\n"
        "⚠️ 读到的都是**初始密码**。如果你已经改过密码，这里显示的是旧值，"
        "**以你改后的为准**。"
    )

    ui.markdown("**各服务的端口**（从外网访问时，端口换成你在云控制台映射的那个）")
    for name, port, hint in credentials.PORTS:
        line = f"- {name}：`{port}`"
        if hint:
            line += f"　—　{hint}"
        ui.markdown(line)

    box = ui.column().classes("w-full")

    async def refresh():
        box.clear()
        with box:
            ui.label("读取中 ...")
        try:
            rows = await credentials.gather()
        except Exception as exc:
            box.clear()
            with box:
                ui.label(f"读取失败：{exc}")
            return
        box.clear()
        with box:
            for r in rows:
                with ui.row().classes("items-center gap-2 no-wrap"):
                    ui.label(f"{r['name']}（{r['port']}）").classes("w-52")
                    if r["ok"]:
                        ui.label(r["value"]).classes("font-mono text-base")
                        ui.button(
                            icon="content_copy",
                            on_click=lambda v=r["value"]: ui.run_javascript(
                                f"navigator.clipboard.writeText({v!r})"
                            ),
                        ).props("flat dense")
                    else:
                        ui.label("—— 没读到").classes("text-gray-500")
                ui.label(r["note"]).classes("text-xs text-gray-500")

    ui.button("读取 / 刷新", on_click=refresh)


@ui.page("/")
def index():
    global LOG
    ui.markdown("# 图恒宇计划 · 部署面板")
    ui.markdown("按顺序点。**先体检**，再配源，然后装东西。")

    with ui.row():
        ui.button("① 环境体检", on_click=_handler("环境体检", CHECK_CMDS))
        ui.button("② 安装 Docker", on_click=_handler("安装 Docker", DOCKER_CMDS))
        ui.button(
            "③ 安装 SnowLuma",
            on_click=_dynamic_handler(
                "安装 SnowLuma",
                lambda: snowluma_cmds(
                    STATE["proxy"]["prefix"] if STATE["proxy"] else ""
                ),
            ),
        )
        ui.button("④ 安装 AstrBot", on_click=_handler("安装 AstrBot", ASTRBOT_CMDS))
        ui.button("⑤ 连线（待实现）", on_click=lambda: ui.notify("待实现", type="info"))

    with ui.expansion("网络源（测速 / 自动选优）", value=True):
        source_section()

    with ui.expansion("找不到密码？点这里读初始凭据", value=False):
        credential_section()

    LOG = ui.log(max_lines=4000).classes("w-full h-96")


# ---------- 认证：面板能执行命令，公网暴露前必须挡一道 ----------
PANEL_USER = os.environ.get("PANEL_USER", "admin")
PANEL_PASS = os.environ.get("PANEL_PASS", "")


@app.middleware("http")
async def _basic_auth(request, call_next):
    # 没设密码就不拦（本地/内网调试用）；设了就必须带 Basic 认证
    if not PANEL_PASS:
        return await call_next(request)
    expected = "Basic " + base64.b64encode(
        f"{PANEL_USER}:{PANEL_PASS}".encode()
    ).decode()
    if request.headers.get("authorization") != expected:
        return _Resp(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="tuhengyu"'},
        )
    return await call_next(request)


ui.run(host="0.0.0.0", port=8080, title="图恒宇计划", reload=False)