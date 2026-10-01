"""图恒宇计划 · 部署面板（NiceGUI）

v0.3（2026-10-01）：界面重做 —— 深色主题、响应式（手机可用）、凭据表格化。

外观设计的三条约束：
  1. 目标机器**无国际出口**，所以**不能引用任何外部资源**（CDN / 外链字体 / 外链图）。
     全部样式内联；图标用内联 SVG 或 NiceGUI 自带的本地字体图标。
  2. 面板**跑在 http 上**（非安全上下文），`navigator.clipboard` 不可用，
     复制必须走 `execCommand` 回退。
  3. 手机屏幕窄，按钮要能换行、表格要能横向滚动。
"""
import asyncio
import base64
import html as _html
import json
import os
import secrets

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

# ---------------------------------------------------------------- 外观

# 自绘 SVG（无版权问题，无外部依赖）：一颗行星 + 两条轨道
LOGO_SVG = """
<svg viewBox="0 0 48 48" width="38" height="38" fill="none" aria-hidden="true">
  <defs>
    <linearGradient id="tg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#22d3ee"/>
      <stop offset="1" stop-color="#818cf8"/>
    </linearGradient>
  </defs>
  <circle cx="24" cy="24" r="8.5" stroke="url(#tg)" stroke-width="2.4"/>
  <ellipse cx="24" cy="24" rx="19" ry="7.5" stroke="url(#tg)" stroke-width="1.5"
           opacity="0.8" transform="rotate(-18 24 24)"/>
  <ellipse cx="24" cy="24" rx="19" ry="7.5" stroke="url(#tg)" stroke-width="1.2"
           opacity="0.4" transform="rotate(52 24 24)"/>
  <circle cx="24" cy="24" r="3" fill="url(#tg)"/>
</svg>
"""

CSS = """
/* ---------- 品牌栏 ---------- */
.tg-brand {
  background:
    radial-gradient(1200px 400px at 10% -40%, rgba(34,211,238,.16), transparent 60%),
    radial-gradient(900px 400px at 90% -60%, rgba(129,140,248,.18), transparent 60%);
  border-bottom: 1px solid rgba(148,163,184,.18);
}
.tg-title {
  font-size: 1.4rem; font-weight: 700; letter-spacing: .01em; line-height: 1.2;
  background: linear-gradient(90deg, #22d3ee, #818cf8);
  -webkit-background-clip: text; background-clip: text;
  color: transparent;
}
.tg-sub { font-size: .72rem; opacity: .55; letter-spacing: .08em; }

/* ---------- 卡片 ---------- */
.tg-card {
  border-radius: 16px !important;
  border: 1px solid rgba(148,163,184,.20) !important;
  box-shadow: 0 8px 28px rgba(0,0,0,.10) !important;
}

/* ---------- 步骤按钮 ---------- */
.tg-step {
  border-radius: 12px !important;
  text-transform: none !important;
  font-weight: 600 !important;
  letter-spacing: .01em !important;
}

/* 图标与中文混排的对齐：
   Material Icons 的字形基线是按英文调的，与中文并排时容易显得上下不齐。
   统一 flex 居中 + 图标略放大 + 明确间距。
   横向改左对齐：按钮撑满整行时，居中对齐会让每个按钮的图标各自偏移，
   竖向扫读呈锯齿状；左对齐后图标落在同一条竖线上。 */
.tg-step .q-btn__content {
  align-items: center !important;
  justify-content: flex-start !important;
  text-align: left !important;
  width: 100% !important;
  line-height: 1.35 !important;
  gap: 6px !important;
  padding-left: 6px !important;
  padding-right: 6px !important;
}
.tg-step .q-icon {
  font-size: 1.2em !important;
  vertical-align: middle !important;
  line-height: 1 !important;
  flex: 0 0 auto;
}
.tg-step .q-btn__content > span {
  display: inline-flex;
  align-items: center;
  line-height: 1.35;
  flex: 1 1 auto;
  text-align: left;
}

/* 品牌栏 logo：行内 SVG 默认按基线对齐，会与标题文字错位 */
.tg-brand svg {
  display: block !important;
  flex: 0 0 auto;
}
/* 卡片标题行里的图标同样处理 */
.tg-headicon { line-height: 1 !important; }

/* ---------- 凭据表 ---------- */
.tg-wrap { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
.tg-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: .93rem; }
.tg-table th {
  text-align: left; padding: 9px 12px;
  font-size: .72rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase;
  opacity: .55; white-space: nowrap;
  border-bottom: 1px solid rgba(148,163,184,.28);
}
.tg-table td {
  padding: 13px 12px; vertical-align: middle;
  border-bottom: 1px solid rgba(148,163,184,.13);
}
.tg-table tbody tr:last-child td { border-bottom: none; }
.tg-table tbody tr:hover { background: rgba(148,163,184,.07); }
.tg-pw {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-weight: 600; letter-spacing: .01em;
  word-break: break-all;
}
.tg-port { opacity: .6; font-family: ui-monospace, monospace; white-space: nowrap; }
.tg-copy {
  border: 1px solid rgba(148,163,184,.35);
  background: transparent; color: inherit;
  border-radius: 8px; padding: 4px 11px; font-size: .8rem; cursor: pointer;
  transition: all .15s; white-space: nowrap;
}
.tg-copy:hover { border-color: #22d3ee; color: #22d3ee; }
.tg-copy:active { transform: scale(.95); }
.tg-none { opacity: .45; }
.tg-note {
  margin-top: 10px; padding: 10px 12px; border-radius: 10px; font-size: .82rem;
  line-height: 1.65;
  background: rgba(251,191,36,.10);
  border: 1px solid rgba(251,191,36,.28);
}

/* ---------- 日志 ---------- */
.tg-log {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace !important;
  font-size: .76rem !important; line-height: 1.5 !important;
  border-radius: 12px !important;
  background: rgba(2,6,23,.55) !important;
}

/* ---------- 手机 ---------- */
@media (max-width: 640px) {
  .tg-title { font-size: 1.12rem; }
  .tg-brand { padding: 12px 14px !important; }
  .tg-step { width: 100%; }
  .tg-hide-sm { display: none !important; }
  .tg-table { font-size: .84rem; }
  .tg-table th { padding: 7px 8px; font-size: .66rem; }
  .tg-table td { padding: 10px 8px; }
  .tg-card { border-radius: 13px !important; }
}
"""

# 复制函数：http 下 navigator.clipboard 不可用，必须回退到 execCommand
COPY_JS = """
<script>
function tgCopy(btn, text) {
  const ok = () => {
    const old = btn.textContent;
    btn.textContent = '已复制';
    setTimeout(() => { btn.textContent = old; }, 1200);
  };
  const legacy = () => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-1000px';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); ok(); }
    catch (e) { btn.textContent = '复制失败'; }
    document.body.removeChild(ta);
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(ok).catch(legacy);
  } else {
    legacy();
  }
}
</script>
"""


def apply_style() -> None:
    ui.add_head_html(f"<style>{CSS}</style>")
    ui.add_head_html(COPY_JS)


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


# ---------------------------------------------------------------- 网络源

def source_section():
    ui.markdown(
        "国内直连 docker / github 常常不通。点测速，面板会并发测所有候选，"
        "自动预选延迟最低的可用线路；**也可以手动点选**。\n\n"
        "⚠️ 候选来自公开列表，**未逐一实测**；国内公共 Docker 镜像曾大面积停服，"
        "**以每次测速结果为准**。失效项请在 `core/sources.py` 里增删。"
    )
    mirror_status = ui.label("镜像加速：未选（先测速，再点选）")
    proxy_status = ui.label("GitHub 加速：未选")

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

    ui.button("一键测速并自动选优", icon="speed", on_click=speedtest).classes("tg-step")

    ui.label("↓ 点一下选中要用的镜像（测速后可改）").classes("text-xs opacity-60")
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

    ui.button(
        "应用镜像加速",
        icon="settings_suggest",
        on_click=apply_mirror,
    ).classes("tg-step")
    ui.label("会写入 daemon.json 并重启 Docker").classes("text-xs opacity-55")


# ---------------------------------------------------------------- 凭据

def _cred_table_html(rows: list) -> str:
    out = [
        '<div class="tg-wrap"><table class="tg-table"><thead><tr>',
        "<th>服务</th><th>端口</th><th>初始密码</th><th></th>",
        "</tr></thead><tbody>",
    ]
    for r in rows:
        name = _html.escape(r["name"])
        if r["ok"]:
            pw = _html.escape(r["value"])
            quoted = json.dumps(r["value"])  # 安全地嵌入 onclick
            out.append(
                f"<tr><td>{name}</td>"
                f'<td class="tg-port">{r["port"]}</td>'
                f'<td class="tg-pw">{pw}</td>'
                f'<td><button class="tg-copy" '
                f"onclick='tgCopy(this, {quoted})'>复制</button></td></tr>"
            )
        else:
            out.append(
                f"<tr><td>{name}</td>"
                f'<td class="tg-port">{r["port"]}</td>'
                f'<td class="tg-none">没读到</td><td></td></tr>'
            )
    out.append("</tbody></table></div>")
    out.append(
        '<div class="tg-note">'
        "⚠️ 读到的都是<b>初始密码</b>。若你已改过密码，这里显示的是旧值，"
        "<b>以你改后的为准</b>。"
        "<br>其中 SnowLuma 若一直没改密，<b>重启会重新生成一个新密码</b>。"
        "</div>"
    )
    return "".join(out)


def _port_table_html() -> str:
    out = [
        '<div class="tg-wrap"><table class="tg-table"><thead><tr>',
        "<th>服务</th><th>内部端口</th><th>说明</th>",
        "</tr></thead><tbody>",
    ]
    for name, port, hint in credentials.PORTS:
        out.append(
            f"<tr><td>{_html.escape(name)}</td>"
            f'<td class="tg-port">{port}</td>'
            f"<td>{_html.escape(hint) or '—'}</td></tr>"
        )
    out.append("</tbody></table></div>")
    out.append(
        '<div class="tg-note">'
        "从外网访问时，把<b>内部端口</b>换成你在云服务商控制台映射的<b>外部端口</b>。"
        "</div>"
    )
    return "".join(out)


def credential_section():
    ui.markdown(
        "装完之后，各家控制台的密码分散在**容器日志**和**环境变量**里，"
        "新手很难找到。点下面的按钮，面板替你读出来。"
    )

    box = ui.column().classes("w-full")

    async def refresh():
        box.clear()
        with box:
            ui.spinner(size="lg")
        try:
            rows = await credentials.gather()
        except Exception as exc:
            box.clear()
            with box:
                ui.label(f"读取失败：{exc}")
            return
        box.clear()
        with box:
            ui.html(_cred_table_html(rows), sanitize=False)

    ui.button("读取 / 刷新", icon="key", on_click=refresh).classes("tg-step")

    ui.label("各服务的端口").classes("text-sm font-semibold mt-4 opacity-80")
    ui.html(_port_table_html(), sanitize=False)


# ---------------------------------------------------------------- 首页

@ui.page("/")
def index():
    global LOG
    apply_style()

    # 品牌栏
    with ui.row().classes("tg-brand w-full items-center gap-3 px-5 py-4 no-wrap"):
        ui.html(LOGO_SVG, sanitize=False)
        with ui.column().classes("gap-0"):
            ui.label("图恒宇计划").classes("tg-title")
            ui.label("DEPLOY PANEL").classes("tg-sub")
        ui.space()
        ui.label("给 bot 完整的一生").classes("tg-sub tg-hide-sm")
        ui.button(icon="contrast", on_click=ui.dark_mode().toggle).props(
            "flat round dense"
        ).tooltip("切换深浅色")

    # 主区
    with ui.column().classes("w-full max-w-5xl mx-auto gap-4 p-4"):

        with ui.card().classes("tg-card w-full"):
            ui.label("部署步骤").classes("text-sm font-semibold opacity-70")
            with ui.row().classes("gap-2 w-full"):
                ui.button(
                    "① 环境体检",
                    icon="health_and_safety",
                    on_click=_handler("环境体检", CHECK_CMDS),
                ).classes("tg-step")
                ui.button(
                    "② 安装 Docker",
                    icon="inventory_2",
                    on_click=_handler("安装 Docker", DOCKER_CMDS),
                ).classes("tg-step")
                ui.button(
                    "③ 安装 SnowLuma",
                    icon="chat",
                    on_click=_dynamic_handler(
                        "安装 SnowLuma",
                        lambda: snowluma_cmds(
                            STATE["proxy"]["prefix"] if STATE["proxy"] else ""
                        ),
                    ),
                ).classes("tg-step")
                ui.button(
                    "④ 安装 AstrBot",
                    icon="smart_toy",
                    on_click=_handler("安装 AstrBot", ASTRBOT_CMDS),
                ).classes("tg-step")
                ui.button(
                    "⑤ 连线（待实现）",
                    icon="link_off",
                    on_click=lambda: ui.notify("待实现", type="info"),
                ).classes("tg-step")

        with ui.expansion("网络源（测速 / 自动选优）", icon="tune", value=True).classes(
            "tg-card w-full"
        ):
            source_section()

        with ui.expansion("找不到密码？点这里读初始凭据", icon="key", value=False).classes(
            "tg-card w-full"
        ):
            credential_section()

        with ui.card().classes("tg-card w-full"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("terminal").classes("opacity-60")
                ui.label("运行日志").classes("text-sm font-semibold opacity-70")
            LOG = ui.log(max_lines=4000).classes("tg-log w-full h-80")


# ---------- 认证：面板能执行命令，公网暴露前必须挡一道 ----------
#
# 安全默认（2026-10-01 补）：
#   原来若没设 PANEL_PASS，中间件直接放行 —— 也就是**没有登录框**。
#   而面板能执行任意系统命令（装 Docker、改 daemon.json），
#   公网暴露等于把 root 挂上网。多次实测确认过这个洞。
#
#   现在改为三级回退，保证「绝不会无密码运行」：
#     1. 环境变量 PANEL_PASS（systemd / 手动）
#     2. 安装目录下的 .panel_pass 文件（首次自动生成并保存，重启后不变）
#     3. 实在存不下（只读目录）→ 用内存里的随机值，并明确警告会变

PANEL_USER = os.environ.get("PANEL_USER", "admin") or "admin"
_PASS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".panel_pass")


def _resolve_panel_pass() -> str:
    env = os.environ.get("PANEL_PASS", "").strip()
    if env:
        return env

    if os.path.exists(_PASS_FILE):
        try:
            with open(_PASS_FILE, encoding="utf-8") as f:
                saved = f.read().strip()
            if saved:
                return saved
        except OSError:
            pass

    generated = secrets.token_urlsafe(12)
    try:
        with open(_PASS_FILE, "w", encoding="utf-8") as f:
            f.write(generated)
        os.chmod(_PASS_FILE, 0o600)
    except OSError as exc:
        print(f"[图恒宇] 警告：无法保存自动生成的密码（{exc}），本次重启后会变。")
    return generated


PANEL_PASS = _resolve_panel_pass()


def _announce_password() -> None:
    """没走环境变量时，把自动生成的密码明确打出来，别让人找不到。"""
    if os.environ.get("PANEL_PASS", "").strip():
        return
    print("=" * 64)
    print("[图恒宇] 未通过环境变量设置面板密码。")
    print(f"[图恒宇] 已自动生成并写入：{_PASS_FILE}")
    print(f"[图恒宇]   用户名: {PANEL_USER}")
    print(f"[图恒宇]   密  码: {PANEL_PASS}")
    print("[图恒宇] 想换成自己的密码：编辑 /etc/systemd/system/tuhengyu-panel.service")
    print("[图恒宇]   里的 PANEL_PASS，再 systemctl daemon-reload && systemctl restart tuhengyu-panel")
    print("=" * 64)


_announce_password()


@app.middleware("http")
async def _basic_auth(request, call_next):
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