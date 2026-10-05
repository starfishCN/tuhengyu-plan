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
import hashlib
import hmac
import html as _html
import json
import os
import secrets
import urllib.parse

from nicegui import app, ui
from fastapi.responses import Response as _Resp

from core.runner import run_stream_all
from core.check import CHECK_CMDS
from core.docker import DOCKER_CMDS, apply_mirror_cmds
from core.snowluma import snowluma_cmds
from core.astrbot import ASTRBOT_CMDS
from core import sources
from core import credentials
from core.plugin import PLUGIN_INSTALL_CMDS

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
/* ---------- 基础：防白闪 + 背景光斑 ----------
   页面加载瞬间会先显示浏览器默认背景。深色面板上那是一道刺眼的白闪，
   所以在 html 层就压住底色。
   body 上的两团光斑不只是装饰 —— 按钮的毛玻璃（backdrop-filter）需要
   背后有明暗变化才看得出来，纯色背景上它等于没有效果。 */
html { background-color: #0b1020; }
body {
  background-color: #0b1020;
  background-image:
    radial-gradient(1100px 700px at 12% -5%, rgba(34,211,238,.10), transparent 55%),
    radial-gradient(900px 700px at 88% -12%, rgba(129,140,248,.13), transparent 55%),
    radial-gradient(800px 600px at 50% 115%, rgba(56,189,248,.07), transparent 60%);
  background-repeat: no-repeat;
  background-attachment: fixed;
}
body.body--light {
  background-color: #f1f5f9;
  background-image:
    radial-gradient(1100px 700px at 12% -5%, rgba(34,211,238,.14), transparent 55%),
    radial-gradient(900px 700px at 88% -12%, rgba(129,140,248,.16), transparent 55%);
}

/* ---------- 入场动画 ----------
   为什么改了三版（记下来，免得下次又走回头路）：

   v1 用 CSS animation —— 面板是**客户端渲染**，元素插入 DOM 时动画即开始
      计时，而容器此时还藏着，等显示出来动画早跑完了 → 看不到。

   v2 「检测到可见后加 class 走 transition」—— 机制本来是对的，但有两个
      真凶把它盖住了（见下）。

   v3 「倒带式重播」—— 为绕开时序判断，让元素先显示再打回起点重播。
      能跑，但**会先闪一下完整内容**才播动画，观感是错的。已废弃。

   → 现在回到 v2 的路子，并修掉两个真凶：

   真凶一：前几版都写了 `@media (prefers-reduced-motion: reduce)`，把动画
           整个关掉 —— 用户系统开着「减弱动态效果」时，三代全都不动。
           已移除（私有面板，按要求强制播放）。

   真凶二：v2 里的「超时放行」会在元素出现**之前**就加上 class，等于把动画
           自己取消了。已移除 —— 脚本万一没跑，由 CSS 的 3 秒兜底负责显示。

   时序：元素从插入 DOM 起就是透明的（下面设了初始隐藏）→ JS 检测到它真的
   有高度了 → 加 .tg-in → 淡入。全程**不会闪出完整内容**。

   曲线：0.8s + easeOutQuart —— 比 v3 的 .6s + easeOutQuint 更缓，
   起手不猛、收尾柔和。 */

@keyframes tg-force {
  to { opacity: 1; filter: blur(0); }
}

/* 不用位移，只用 opacity + blur —— 模糊逐渐收实，就是「凝聚成形」的感觉。
   filter 只在「未放行」状态下声明，放行后回到默认的 none，
   这样动画结束后元素身上没有 filter，不会影响内部按钮的 backdrop-filter。 */
.tg-brand,
.tg-main > * {
  transition: opacity 1.2s cubic-bezier(.25,.46,.45,.94),
              filter 1.2s cubic-bezier(.25,.46,.45,.94);
}
/* 卡片错开，像一层层凝出来 */
.tg-main > *:nth-child(1) { transition-delay: .1s; }
.tg-main > *:nth-child(2) { transition-delay: .2s; }
.tg-main > *:nth-child(3) { transition-delay: .3s; }
.tg-main > *:nth-child(4) { transition-delay: .4s; }
.tg-main > *:nth-child(5) { transition-delay: .5s; }
.tg-main > *:nth-child(6) { transition-delay: .6s; }
.tg-main > *:nth-child(n+7) { transition-delay: .68s; }

html:not(.tg-in) .tg-brand { opacity: 0; filter: blur(6px); }
html:not(.tg-in) .tg-main > * { opacity: 0; filter: blur(6px); }

/* 兜底：脚本若没跑，3 秒后强制显示（否则会一直停在透明状态） */
html:not(.tg-in) .tg-brand,
html:not(.tg-in) .tg-main > * {
  animation: tg-force .5s ease 3s forwards;
}

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

/* ---------- 步骤按钮：毛玻璃 ---------- */
.tg-step {
  border-radius: 12px !important;
  text-transform: none !important;
  font-weight: 600 !important;
  letter-spacing: .01em !important;
  /* 半透明渐变 + 背后模糊 = 玻璃质感。
     渐变做出「上缘受光」的错觉，内阴影补一道高光边。 */
  background: linear-gradient(180deg, rgba(255,255,255,.10), rgba(255,255,255,.035)) !important;
  border: 1px solid rgba(255,255,255,.14) !important;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.13),
    0 4px 14px rgba(0,0,0,.22) !important;
  backdrop-filter: blur(10px) saturate(150%);
  -webkit-backdrop-filter: blur(10px) saturate(150%);
  transition: background .2s, border-color .2s, box-shadow .2s !important;
}
.tg-step:hover {
  background: linear-gradient(180deg, rgba(255,255,255,.15), rgba(255,255,255,.06)) !important;
  border-color: rgba(34,211,238,.38) !important;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.18),
    0 6px 20px rgba(34,211,238,.14) !important;
}
.tg-step:active { transform: translateY(1px); }

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
  border: 1px solid rgba(255,255,255,.16);
  background: linear-gradient(180deg, rgba(255,255,255,.09), rgba(255,255,255,.03));
  backdrop-filter: blur(8px) saturate(140%);
  -webkit-backdrop-filter: blur(8px) saturate(140%);
  color: inherit;
  border-radius: 8px; padding: 4px 11px; font-size: .8rem; cursor: pointer;
  transition: all .15s; white-space: nowrap;
}
.tg-copy:hover {
  border-color: rgba(34,211,238,.5);
  color: #22d3ee;
  background: linear-gradient(180deg, rgba(34,211,238,.12), rgba(34,211,238,.04));
}
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

# 入场动画触发器。
#
# 时序要点：元素**从插入 DOM 那一刻**起就是透明的（CSS 里 html:not(.tg-in)
# 设了初始隐藏），所以不会先闪出完整内容。JS 只负责在确认它真的渲染出来
# 之后，加上 .tg-in 放行。
#
# 两个踩过的坑：
#   · 不要设「超时提前放行」—— 那会在元素出现之前就加 class，等于取消动画。
#     脚本万一没跑，由 CSS 的 3 秒兜底动画负责显示。
#   · 不要「倒带重播」（先正常显示、再打回起点）—— 能跑，但会先闪一下完整内容。
ENTER_JS = """
<script>
(function () {
  var root = document.documentElement;
  var fired = false;
  function fire() {
    if (fired) { return; }
    fired = true;
    root.classList.add('tg-in');
  }

  var tries = 0;
  var iv = setInterval(function () {
    tries++;
    var el = document.querySelector('.tg-main');
    var ok = el
      && document.readyState !== 'loading'
      && el.getBoundingClientRect().height > 0;
    if (ok) {
      clearInterval(iv);
      // 等两帧，确保初始隐藏已被浏览器采纳，transition 才有起点
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { fire(); });
      });
    } else if (tries > 750) {
      // 30 秒还没就绪就停手，交给 CSS 兜底显示，绝不把面板锁在透明状态
      clearInterval(iv);
    }
  }, 40);
})();
</script>
"""


def apply_style() -> None:
    ui.add_head_html(f"<style>{CSS}</style>")
    ui.add_head_html(COPY_JS)
    ui.add_head_html(ENTER_JS)


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

    async def speedtest_and_apply():
        # 真小白入口：测速、选优、写配置一次完成。
        if not _guard():
            return
        LOG.push("===== 一键测速并应用最优 Docker 源 =====")
        try:
            results = await sources.test_all(sources.DOCKER_MIRRORS, sources.docker_mirror_url)
            best = sources.pick_best(results)
            if not best:
                LOG.push("!! 没有可用的 Docker 镜像源")
                ui.notify("没有可用镜像源，请换线路或使用代理/镜像中转", type="negative")
                return
            mirror_select.value = best["url"]
            mirror_select.update()
            mirror_status.text = f"镜像加速：{best['name']}（已自动选中）"
            await _run("应用最优 Docker 镜像加速", apply_mirror_cmds(best["url"]))
        finally:
            # _run 会释放 busy；若测速阶段提前结束，这里负责释放。
            STATE["busy"] = False
            LOG.push("===== 一键测速并应用最优 Docker 源结束 =====")

    ui.button(
        "小白模式：自动测速并应用",
        icon="auto_fix_high",
        on_click=speedtest_and_apply,
    ).props("color=primary").classes("tg-step")
    ui.label("不需要手动挑选，成功后再安装 Docker").classes("text-xs opacity-55")


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

async def _logout() -> None:
    # 清 Cookie 必须由服务端做，所以整页跳转；不能用 SPA 路由（那不会发请求）
    await ui.run_javascript("window.location.href = '/logout';")


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
        ui.button(icon="logout", on_click=_logout).props(
            "flat round dense"
        ).tooltip("退出登录")

    # 主区
    with ui.column().classes("tg-main w-full max-w-5xl mx-auto gap-4 p-4"):

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
                ui.button(
                    "⑥ 装配套插件",
                    icon="extension",
                    on_click=_handler("装配套插件", PLUGIN_INSTALL_CMDS),
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


# ---------------------------------------------------------------- 认证
#
# 为什么不用 HTTP Basic Auth（2026-10-01 改）：
#   Basic Auth 的登录框由**浏览器**绘制，样式完全不可控 —— 在深色面板上
#   突然弹出一个系统样式的白框，观感断裂。而且它每个请求都要重发明文凭据。
#
# 现在改为：自建登录页 + HMAC 签名会话 Cookie。
#   · 未登录的页面请求        → 303 跳 /login
#   · 密码正确                → 下发 HttpOnly 会话 Cookie（7 天）
#   · 密钥由 PANEL_PASS 派生  → 改密码即让全部旧会话立即失效
#
# 放行边界（写错会「裸奔」或「自我锁死」）：
#   · /login /logout          放行 —— 登录页本身是纯 HTML，不依赖 NiceGUI
#   · /_nicegui/ 静态资源     放行 —— 只是 JS / CSS / 字体文件，无机密
#   · /socket.io 实时通道     **必须带 Cookie** —— 页面数据走这条通道推送，
#                             拦不住它等于没拦。
#   · 其余一切                必须带 Cookie，否则跳登录页

# ------------------------------------------------------ 首次强制改密（2026-10-03）
#
# 起因：安装脚本原先把默认密码**写死在仓库里**（`admin` + 固定值），
# 而面板能执行任意系统命令 —— 公网上一扫就能进。仓库里出现明文口令
# 也直接踩了「公开产物不留凭据」的线。
#
# 现在改为三段式：
#   1. 安装时**随机生成**初始密码，只在安装终端打印一次，不进仓库；
#   2. 首次登录**强制改密**，没改完不放行任何页面；
#   3. 新密码以「随机盐 + SHA-256」存 `.panel_auth.json`（0600）。
#
# 为什么不再依赖环境变量：`systemctl show`、`/proc/<pid>/environ`
# 都能把 Environment= 里的明文读出来。

_AUTH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".panel_auth.json")


def _load_auth():
    try:
        with open(_AUTH_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and data.get("user") and data.get("salt") and data.get("hash"):
        return data
    return None


def _hash_pwd(salt: str, pwd: str) -> str:
    return hashlib.sha256(f"{salt}|{pwd}".encode()).hexdigest()


def _save_auth(user: str, pwd: str) -> bool:
    salt = secrets.token_hex(16)
    payload = {"user": user, "salt": salt, "hash": _hash_pwd(salt, pwd)}
    tmp = _AUTH_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, _AUTH_FILE)
        return True
    except OSError as exc:
        print(f"[图恒宇] 警告：改密失败，无法写入 {_AUTH_FILE}（{exc}）")
        return False


def _check_login(user: str, pwd: str) -> bool:
    saved = _load_auth()
    if saved:
        ok_u = hmac.compare_digest(user, saved["user"])
        ok_p = hmac.compare_digest(_hash_pwd(saved["salt"], pwd), saved["hash"])
    else:
        ok_u = hmac.compare_digest(user, PANEL_USER)
        ok_p = hmac.compare_digest(pwd, PANEL_PASS)
    return ok_u & ok_p


def _must_change() -> bool:
    """还没设过自己的密码 → 必须先改密才放行。"""
    return _load_auth() is None


COOKIE_NAME = "tg_session"

# 最少密码长度。面板能装 Docker、改 daemon.json，别用 6 位糊弄。
MIN_PWD_LEN = 8


def _session_token() -> str:
    """会话密钥随密码变化 —— 改完密码，所有旧会话立即失效。"""
    saved = _load_auth()
    secret = saved["hash"] if saved else f"tuhengyu|{PANEL_PASS}"
    return hmac.new(
        hashlib.sha256(secret.encode()).digest(),
        b"panel-session",
        hashlib.sha256,
    ).hexdigest()

_LOGIN_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>登录 · 图恒宇计划</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; padding: 24px;
    display: flex; align-items: center; justify-content: center;
    font-family: system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #e2e8f0; background-color: #0b1020;
    background-image:
      radial-gradient(900px 500px at 12% -10%, rgba(34,211,238,.15), transparent 60%),
      radial-gradient(800px 520px at 88% -18%, rgba(129,140,248,.17), transparent 60%);
  }
  @keyframes tg-enter {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @media (prefers-reduced-motion: reduce) { .card { animation: none !important; } }
  .card {
    animation: tg-enter .45s cubic-bezier(.22,1,.36,1) both;
    width: 100%; max-width: 372px; padding: 34px 28px 26px;
    background: rgba(18,25,44,.92);
    border: 1px solid rgba(148,163,184,.16);
    border-radius: 18px;
    box-shadow: 0 24px 60px rgba(0,0,0,.55);
  }
  .brand { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
  .brand svg { display: block; flex: 0 0 auto; }
  .name {
    font-size: 1.16rem; font-weight: 700; letter-spacing: .02em;
    background: linear-gradient(90deg, #22d3ee, #818cf8);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  .sub { margin: 0 0 24px; font-size: .82rem; color: #94a3b8; letter-spacing: .03em; }
  label { display: block; font-size: .78rem; color: #94a3b8; margin: 0 0 7px; letter-spacing: .04em; }
  input {
    width: 100%; padding: 12px 13px; margin-bottom: 18px;
    font-size: .95rem; color: #e2e8f0; background: rgba(11,16,32,.85);
    border: 1px solid rgba(148,163,184,.22); border-radius: 10px; outline: none;
    transition: border-color .15s, box-shadow .15s;
  }
  input:focus { border-color: #22d3ee; box-shadow: 0 0 0 3px rgba(34,211,238,.14); }
  button {
    width: 100%; padding: 12px; margin-top: 4px;
    font-size: .95rem; font-weight: 600; letter-spacing: .14em; color: #06121f;
    background: linear-gradient(90deg, #22d3ee, #818cf8);
    border: 0; border-radius: 10px; cursor: pointer;
    transition: filter .15s, transform .06s;
  }
  button:hover { filter: brightness(1.08); }
  button:active { transform: translateY(1px); }
  .err {
    margin: 0 0 18px; padding: 9px 12px; font-size: .83rem;
    color: #fca5a5; background: rgba(248,113,113,.10);
    border: 1px solid rgba(248,113,113,.28); border-radius: 9px;
  }
  .foot { margin: 22px 0 0; font-size: .72rem; color: #64748b; text-align: center; }
</style>
</head>
<body>
  <div class="card">
    <div class="brand">
      __LOGO__
      <div class="name">图恒宇计划</div>
    </div>
    <p class="sub">__SUB__</p>
    __ERR__
    __FORM__
    <p class="foot">图恒宇计划 · 部署面板</p>
  </div>
</body>
</html>
"""


_LOGIN_FORM = """
    <form method="post" action="/login">
      <label for="u">用户名</label>
      <input id="u" name="username" autocomplete="username" autofocus required>
      <label for="p">密码</label>
      <input id="p" name="password" type="password" autocomplete="current-password" required>
      <button type="submit">登录</button>
    </form>
"""

_SETPWD_FORM = """
    <form method="post" action="/set-password">
      <label for="p1">新密码（至少 __MIN__ 位）</label>
      <input id="p1" name="password" type="password" autocomplete="new-password" autofocus required>
      <label for="p2">再输一遍</label>
      <input id="p2" name="password2" type="password" autocomplete="new-password" required>
      <button type="submit">设好了</button>
    </form>
"""


def _render_page(sub: str, form: str, error: str = "") -> str:
    err = f'<div class="err">{_html.escape(error)}</div>' if error else ""
    return (
        _LOGIN_TPL.replace("__LOGO__", LOGO_SVG)
        .replace("__SUB__", _html.escape(sub))
        .replace("__FORM__", form)
        .replace("__ERR__", err)
    )


def _login_page(error: str = "") -> str:
    return _render_page("给 bot 完整的一生", _LOGIN_FORM, error)


def _setpwd_page(error: str = "") -> str:
    return _render_page(
        "初始密码是一次性的，先改成自己的",
        _SETPWD_FORM.replace("__MIN__", str(MIN_PWD_LEN)),
        error,
    )


def _has_session(request) -> bool:
    return hmac.compare_digest(request.cookies.get(COOKIE_NAME, ""), _session_token())


def _grant(target: str) -> _Resp:
    """下发会话 Cookie 并跳转。"""
    resp = _Resp(status_code=303, headers={"Location": target})
    resp.set_cookie(
        COOKIE_NAME, _session_token(),
        max_age=7 * 24 * 3600, httponly=True, samesite="lax", path="/",
    )
    return resp


@app.middleware("http")
async def _auth(request, call_next):
    path = request.url.path

    # --- 登录 / 登出：中间件直接处理，不进 NiceGUI ---
    if path == "/login":
        if request.method == "GET":
            return _Resp(_login_page(), media_type="text/html")
        body = (await request.body()).decode("utf-8", "replace")
        form = urllib.parse.parse_qs(body)
        user = form.get("username", [""])[0]
        pwd = form.get("password", [""])[0]
        if not _check_login(user, pwd):
            return _Resp(_login_page("用户名或密码不对"), media_type="text/html")
        # 初始密码一律视为临时密码 → 先改密，改完才放行
        return _grant("/set-password" if _must_change() else "/")

    # --- 改密页：本身就是「首次强制改密」的落点 ---
    if path == "/set-password":
        if not _has_session(request):
            return _Resp(status_code=303, headers={"Location": "/login"})
        if request.method == "GET":
            return _Resp(_setpwd_page(), media_type="text/html")
        body = (await request.body()).decode("utf-8", "replace")
        form = urllib.parse.parse_qs(body)
        p1 = form.get("password", [""])[0]
        p2 = form.get("password2", [""])[0]
        if len(p1) < MIN_PWD_LEN:
            return _Resp(_setpwd_page(f"至少 {MIN_PWD_LEN} 位"), media_type="text/html")
        if p1 != p2:
            return _Resp(_setpwd_page("两次输入不一致"), media_type="text/html")
        saved = _load_auth()
        if not _save_auth(saved["user"] if saved else PANEL_USER, p1):
            return _Resp(
                _setpwd_page("写入失败：面板目录不可写，改用 chattr / 手动建 .panel_auth.json"),
                media_type="text/html",
            )
        # 会话密钥由密码派生 → 这里必须重新下发，否则自己会被踢出去
        return _grant("/")

    if path == "/logout":
        resp = _Resp(status_code=303, headers={"Location": "/login"})
        resp.delete_cookie(COOKIE_NAME, path="/")
        return resp

    # --- 首次未改密：除改密页与登出，一律押到 /set-password ---
    if _must_change() and path not in ("/set-password", "/logout"):
        return _Resp(status_code=303, headers={"Location": "/set-password"})

    # --- NiceGUI 静态资源：放行（只有 JS / CSS / 字体，不含数据）---
    if path.startswith("/_nicegui/"):
        return await call_next(request)

    # --- NiceGUI 实时通道：**必须带 Cookie** ---
    # 实测（2026-10-01）：真实挂载点是 /_nicegui_ws/，它**不**匹配上面的
    # /_nicegui/ 前缀（"_nicegui_ws" 与 "_nicegui/" 是两个不同前缀），
    # 所以必须单独判断。这条拦不住 = 页面数据可被未认证者从实时通道拉走。
    if path.startswith("/_nicegui_ws/"):
        if _has_session(request):
            return await call_next(request)
        return _Resp(status_code=303, headers={"Location": "/login"})

    if path.startswith("/favicon.ico"):
        return await call_next(request)

    # --- 其余一切都要会话 Cookie ---
    if _has_session(request):
        return await call_next(request)

    return _Resp(status_code=303, headers={"Location": "/login"})


ui.run(host="0.0.0.0", port=8080, title="图恒宇计划", reload=False)