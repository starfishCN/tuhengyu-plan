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
from core.image_bundle import image_prepare_cmds, bundle_configured
from core import sources
from core import credentials
from core.plugin import PLUGIN_INSTALL_CMDS
from core import offline
from core.post_setup import setup_after_qq_login
STATE = {"busy": False, "mirror": None, "proxy": None}
LOG = None
DEPLOY_VIEW = {"status": None, "stage": None, "progress": None}

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
.tg-status {
  background: rgba(255,255,255,.9) !important;
  border-color: rgba(15,23,42,.08) !important;
}
.tg-status .q-linear-progress {
  height: 8px !important; border-radius: 999px !important;
  background: #e2e8f0 !important; overflow: hidden;
}
.tg-status .q-linear-progress__model {
  border-radius: 999px !important;
  background: linear-gradient(90deg, #0ea5e9, #22c55e) !important;
  transition: width .45s cubic-bezier(.22,1,.36,1) !important;
}
.body--dark .tg-status { background: rgba(15,23,42,.82) !important; }
.body--dark .tg-status .q-linear-progress { background: rgba(148,163,184,.22) !important; }
.tg-status-percent { color: #0284c7; font-variant-numeric: tabular-nums; }
/* 首页主视觉 */
.tg-hero {
  position: relative; overflow: hidden;
  padding: 1.6rem !important;
  background: rgba(255,255,255,.88) !important;
  border-color: rgba(15,23,42,.09) !important;
  box-shadow: 0 18px 50px rgba(15,23,42,.10) !important;
}
.tg-hero::after {
  content: ""; position: absolute; width: 280px; height: 280px; right: -110px; top: -150px;
  border-radius: 50%; background: rgba(56,189,248,.14); filter: blur(3px);
  animation: tg-orbit 9s ease-in-out infinite alternate;
}
@keyframes tg-orbit { to { transform: translate(-35px, 28px) scale(1.12); opacity: .55; } }
.tg-kicker {
  color: #0284c7; font-size: .72rem; font-weight: 800;
  letter-spacing: .13em; text-transform: uppercase;
}
.tg-flow {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px; margin: 18px 0 20px;
}
.tg-flow-item {
  position: relative; min-height: 70px; padding: 13px 14px; border-radius: 12px;
  background: #f8fafc; border: 1px solid #e2e8f0;
  transition: transform .22s ease, border-color .22s ease, box-shadow .22s ease;
}
.tg-flow-item:hover {
  transform: translateY(-3px); border-color: #7dd3fc;
  box-shadow: 0 8px 20px rgba(14,165,233,.12);
}
.tg-flow-item::before { display: none; }
.tg-flow-badge {
  display: inline-grid; place-items: center; width: 28px; height: 28px;
  margin-bottom: 12px; border-radius: 9px;
  color: #fff; font: 800 .82rem ui-monospace, monospace;
  background: linear-gradient(135deg, #0284c7, #4f46e5);
  box-shadow: 0 5px 12px rgba(37,99,235,.25), 0 0 0 4px rgba(14,165,233,.08);
  transition: transform .28s cubic-bezier(.22,1,.36,1), box-shadow .28s ease;
}
.tg-flow-item:hover .tg-flow-badge {
  transform: translateY(-3px) rotate(-6deg) scale(1.08);
  box-shadow: 0 8px 18px rgba(37,99,235,.34), 0 0 0 6px rgba(14,165,233,.12);
}
.tg-flow-text { display: block; color: #0f172a; font-size: .84rem; font-weight: 650; line-height: 1.4; }
.tg-nat {
  display: flex; gap: 10px; align-items: flex-start;
  margin: 14px 0 0; padding: 12px 13px; border-radius: 11px;
  color: #78350f; background: #fffbeb;
  border: 1px solid #fcd34d; line-height: 1.55;
}
.tg-nat strong { color: #b45309; white-space: nowrap; }
.tg-nat small { display: block; opacity: .9; }
.body--dark .tg-hero { background: rgba(15,23,42,.82) !important; border-color: rgba(148,163,184,.2) !important; }
.body--dark .tg-flow-item { background: rgba(30,41,59,.72); border-color: rgba(148,163,184,.22); }
.body--dark .tg-flow-text { color: #e2e8f0; }
.body--dark .tg-flow-badge { box-shadow: 0 5px 14px rgba(37,99,235,.38), 0 0 0 4px rgba(56,189,248,.12); }
@media (max-width: 640px) {
  .tg-flow { grid-template-columns: 1fr; gap: 7px; }
  .tg-flow-item { min-height: 0; padding: 10px 12px; }
  .tg-flow-item::before { display: inline-block; margin: 0 8px 1px 0; }
  .tg-nat { display: block; }
  .tg-nat strong { display: block; margin-bottom: 3px; }
}
/* ---------- 操作按钮：高级感交互 ---------- */
.tg-step, .tg-cta {
  position: relative; overflow: hidden;
  border-radius: 13px !important;
  text-transform: none !important;
  font-weight: 700 !important;
  letter-spacing: .01em !important;
  transition: transform .22s cubic-bezier(.22,1,.36,1),
              box-shadow .22s ease, border-color .22s ease,
              filter .22s ease !important;
}
.tg-step {
  background: linear-gradient(180deg, rgba(255,255,255,.78), rgba(241,245,249,.82)) !important;
  border: 1px solid rgba(15,23,42,.12) !important;
  box-shadow: 0 5px 14px rgba(15,23,42,.10), inset 0 1px 0 rgba(255,255,255,.9) !important;
}
.tg-cta {
  min-height: 64px !important;
  color: #fff !important;
  border: 1px solid rgba(255,255,255,.42) !important;
  box-shadow: 0 10px 22px rgba(14,116,144,.22), inset 0 1px 0 rgba(255,255,255,.4) !important;
}
.tg-cta::before {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(115deg, transparent 25%, rgba(255,255,255,.38) 46%, transparent 66%);
  transform: translateX(-130%); transition: transform .7s cubic-bezier(.16,1,.3,1);
}
.tg-cta::after {
  content: ""; position: absolute; inset: 1px; border-radius: 12px; pointer-events: none;
  border: 1px solid rgba(255,255,255,.18); opacity: .7;
}
.tg-cta-primary { background: linear-gradient(135deg, #0284c7, #2563eb) !important; }
.tg-cta-secondary { background: linear-gradient(135deg, #0891b2, #0f766e) !important; }
.tg-cta:hover, .tg-step:hover {
  transform: translateY(-3px);
  filter: saturate(1.12);
}
.tg-cta:hover {
  box-shadow: 0 16px 30px rgba(14,116,144,.30), 0 0 0 4px rgba(14,165,233,.10), inset 0 1px 0 rgba(255,255,255,.52) !important;
}
.tg-cta:hover::before { transform: translateX(130%); }
.tg-step:hover {
  border-color: rgba(14,165,233,.42) !important;
  box-shadow: 0 10px 22px rgba(14,165,233,.14), inset 0 1px 0 rgba(255,255,255,.95) !important;
}
.tg-cta:active, .tg-step:active {
  transform: translateY(1px) scale(.985);
  transition-duration: .08s !important;
}
.tg-cta .q-icon { animation: tg-icon-idle 3.5s ease-in-out infinite; }
.tg-cta:hover .q-icon { animation: tg-icon-hover .65s ease-in-out infinite alternate; }
@keyframes tg-icon-idle { 0%, 78%, 100% { transform: translateY(0) rotate(0); } 86% { transform: translateY(-2px) rotate(-4deg); } 93% { transform: translateY(0) rotate(3deg); } }
@keyframes tg-icon-hover { to { transform: translateY(-2px) rotate(7deg) scale(1.08); } }
.body--dark .tg-step { background: linear-gradient(180deg, rgba(51,65,85,.9), rgba(30,41,59,.92)) !important; border-color: rgba(148,163,184,.28) !important; }
@media (prefers-reduced-motion: reduce) {
  .tg-cta::before, .tg-cta .q-icon, .tg-hero::after { animation: none !important; transition: none !important; }
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

/* ---------- V2 视觉系统：Infrastructure Control Room ---------- */
:root {
  --ink: #07111f; --panel: rgba(10,21,35,.78); --line: rgba(148,196,220,.18);
  --muted: #8da5b8; --white: #eaf6ff; --cyan: #54e6ff; --mint: #63f5c7;
  --blue: #6687ff; --amber: #ffc857;
}
html, body { background: #050b14 !important; color: var(--white); }
body {
  position: relative; overflow-x: hidden;
  background-image: linear-gradient(rgba(84,230,255,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(84,230,255,.035) 1px, transparent 1px), radial-gradient(ellipse at 20% 0%, rgba(0,173,255,.20), transparent 43%), radial-gradient(ellipse at 92% 18%, rgba(99,245,199,.10), transparent 32%), linear-gradient(135deg, #050b14, #071423 55%, #08111d) !important;
  background-size: 42px 42px, 42px 42px, auto, auto, auto !important; background-attachment: fixed !important;
}
body::before { content: ""; position: fixed; z-index: -1; inset: -30%; pointer-events: none; background: conic-gradient(from 90deg, transparent, rgba(84,230,255,.08), transparent 28%, rgba(99,245,199,.06), transparent 58%); animation: tg-radar 20s linear infinite; }
body::after { content: ""; position: fixed; z-index: -1; left: 0; right: 0; top: -20%; height: 25%; pointer-events: none; background: linear-gradient(180deg, transparent, rgba(84,230,255,.08), transparent); filter: blur(10px); animation: tg-scan 8s ease-in-out infinite; }
@keyframes tg-radar { to { transform: rotate(360deg); } }
@keyframes tg-scan { 0%,100% { transform: translateY(-20vh); opacity: 0; } 35%,65% { opacity: 1; } 100% { transform: translateY(520vh); opacity: 0; } }
.tg-brand { background: rgba(5,12,23,.76) !important; border-bottom: 1px solid var(--line) !important; box-shadow: 0 1px 0 rgba(84,230,255,.06), 0 16px 45px rgba(0,0,0,.22); backdrop-filter: blur(18px); }
.tg-brand::after { content: "SYSTEM / DEPLOYMENT NODE"; margin-left: auto; color: rgba(141,165,184,.58); font: 700 .61rem ui-monospace,monospace; letter-spacing: .16em; }
.tg-title { background: linear-gradient(90deg,#eaf6ff,var(--cyan),var(--mint)) !important; -webkit-background-clip: text !important; background-clip: text !important; }
.tg-sub { color: var(--muted); opacity: 1 !important; }
.tg-main { max-width: 960px !important; padding-top: 2.8rem !important; padding-bottom: 4rem !important; }
.tg-card { background: var(--panel) !important; border: 1px solid var(--line) !important; border-radius: 20px !important; box-shadow: 0 24px 80px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.05) !important; backdrop-filter: blur(20px); }
.tg-hero { padding: 2.1rem !important; background: linear-gradient(135deg,rgba(15,38,57,.92),rgba(8,20,34,.82) 62%,rgba(13,41,48,.88)) !important; border-color: rgba(84,230,255,.28) !important; box-shadow: 0 28px 100px rgba(0,0,0,.42), 0 0 70px rgba(0,173,255,.08) !important; }
.tg-hero::after { width: 420px; height: 420px; right: -180px; top: -250px; background: radial-gradient(circle,rgba(84,230,255,.18),transparent 67%); filter: blur(0); animation: tg-pulse-orbit 8s ease-in-out infinite alternate; }
@keyframes tg-pulse-orbit { to { transform: translate(-80px,80px) scale(1.2); opacity: .45; } }
.tg-kicker { color: var(--cyan) !important; letter-spacing: .24em; }
.tg-flow { position: relative; z-index: 1; gap: 0; margin: 28px 0 24px; padding: 0 4px; }
.tg-flow::before { content: ""; position: absolute; left: 9%; right: 9%; top: 26px; height: 1px; background: linear-gradient(90deg,transparent,var(--cyan),var(--mint),transparent); opacity: .48; }
.tg-flow-item { z-index: 1; min-height: 112px; padding: 15px 14px; background: rgba(3,13,25,.58) !important; border: 1px solid rgba(132,187,213,.19) !important; border-radius: 15px; box-shadow: inset 0 1px 0 rgba(255,255,255,.04); }
.tg-flow-item:hover { transform: translateY(-6px) !important; border-color: rgba(84,230,255,.65) !important; box-shadow: 0 18px 35px rgba(0,0,0,.26), 0 0 28px rgba(84,230,255,.10) !important; }
.tg-flow-badge { width: 38px; height: 38px; margin-bottom: 18px; border-radius: 12px; background: linear-gradient(145deg,var(--cyan),#3372ff 70%) !important; color: #04111e; box-shadow: 0 0 0 1px rgba(84,230,255,.4), 0 0 24px rgba(84,230,255,.25) !important; }
.tg-flow-item:nth-child(2) .tg-flow-badge { background: linear-gradient(145deg,var(--mint),#1e9cba) !important; }
.tg-flow-item:nth-child(3) .tg-flow-badge { background: linear-gradient(145deg,#b3a4ff,#6877ff) !important; }
.tg-flow-text { color: #dcecf5 !important; font-size: .88rem; }
.tg-nat { color: #ffe8a3 !important; background: rgba(104,74,18,.18) !important; border-color: rgba(255,200,87,.35) !important; }
.tg-nat strong { color: var(--amber) !important; }
.tg-cta {
  min-height: 72px !important; border-radius: 15px !important;
  color: #dffaff !important;
  border: 1px solid rgba(112,226,224,.32) !important;
  background: linear-gradient(180deg, rgba(22,48,61,.96), rgba(10,27,40,.98)) !important;
  box-shadow: 0 14px 28px rgba(0,0,0,.28), inset 0 1px 0 rgba(184,255,249,.12), inset 0 0 22px rgba(55,210,196,.05) !important;
}
.tg-cta-primary { border-color: rgba(84,230,255,.48) !important; }
.tg-cta-secondary { border-color: rgba(99,245,199,.42) !important; }
.tg-cta::before { background: linear-gradient(105deg, transparent 30%, rgba(188,255,247,.18) 48%, transparent 67%) !important; }
.tg-cta:hover {
  background: linear-gradient(180deg, rgba(28,63,76,.98), rgba(11,35,46,.99)) !important;
  box-shadow: 0 22px 42px rgba(0,0,0,.38), 0 0 0 1px rgba(112,226,224,.52), 0 0 30px rgba(75,224,201,.13), inset 0 1px 0 rgba(184,255,249,.2) !important;
}
.tg-status { background: rgba(5,16,28,.70) !important; border-color: rgba(99,245,199,.18) !important; }
.tg-status .q-linear-progress { height: 10px !important; background: rgba(141,165,184,.14) !important; box-shadow: inset 0 1px 4px rgba(0,0,0,.32); }
.tg-status .q-linear-progress__model { background: linear-gradient(90deg,var(--cyan),var(--mint)) !important; box-shadow: 0 0 18px rgba(84,230,255,.65); }
.tg-status-percent { color: var(--mint) !important; text-shadow: 0 0 12px rgba(99,245,199,.35); }
.tg-step { color: #cce8f3 !important; background: rgba(12,31,47,.82) !important; border-color: rgba(132,187,213,.24) !important; }
@media (max-width: 640px) { .tg-brand::after { display: none; } .tg-main { padding-top: 1.25rem !important; } .tg-hero { padding: 1.25rem !important; } .tg-flow { gap: 7px; } .tg-flow::before { display: none; } .tg-flow-item { min-height: 0; padding: 11px 12px; } .tg-flow-badge { width: 31px; height: 31px; margin: 0 8px 0 0; vertical-align: middle; } .tg-flow-text { display: inline; } }
"""

# 最终视觉覆盖：必须放在全部旧样式之后，避免主题规则互相覆盖。
CSS += """
/* ---------- Final visual override ---------- */
.tg-flow { position: relative !important; display: grid !important; grid-template-columns: repeat(3, minmax(0, 1fr)) !important; gap: 12px !important; }
.tg-flow::before {
  content: "" !important; display: block !important; position: absolute !important;
  z-index: 0 !important; left: 6% !important; right: 6% !important; top: 34px !important;
  height: 2px !important; border: 0 !important; opacity: 1 !important;
  background: linear-gradient(90deg, transparent, #54e6ff 12%, #63f5c7 50%, #9a8cff 88%, transparent) !important;
  box-shadow: 0 0 8px rgba(84,230,255,.55), 0 0 22px rgba(99,245,199,.24) !important;
  animation: tg-line-breathe 2.8s ease-in-out infinite !important;
}
.tg-flow::after {
  content: "" !important; display: block !important; position: absolute !important;
  z-index: 2 !important; top: 29px !important; left: 6% !important; width: 52px !important; height: 12px !important;
  border-radius: 999px !important; pointer-events: none !important;
  background: linear-gradient(90deg, transparent, #fff, #54e6ff, transparent) !important;
  filter: blur(2px) !important; opacity: .95 !important;
  animation: tg-line-pulse 3.2s cubic-bezier(.45,0,.55,1) infinite !important;
}
@keyframes tg-line-pulse {
  0% { transform: translateX(0); opacity: 0; }
  8% { opacity: 1; }
  70% { opacity: 1; }
  100% { transform: translateX(calc(100% / .88)); opacity: 0; }
}
@keyframes tg-line-breathe { 0%,100% { opacity: .52; } 50% { opacity: 1; } }
.tg-flow-item { position: relative !important; z-index: 3 !important; background: rgba(7,19,31,.96) !important; border: 1px solid rgba(123,183,202,.22) !important; box-shadow: 0 12px 28px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.055) !important; }
.tg-flow-item:hover { border-color: rgba(84,230,255,.78) !important; box-shadow: 0 18px 38px rgba(0,0,0,.38), 0 0 28px rgba(84,230,255,.15) !important; }
.tg-flow-badge { position: relative !important; z-index: 4 !important; background: #0b2532 !important; border: 1px solid #54e6ff !important; color: #bff9ff !important; box-shadow: 0 0 0 4px #071521, 0 0 16px rgba(84,230,255,.42) !important; }
.tg-flow-item:nth-child(2) .tg-flow-badge { border-color: #63f5c7 !important; color: #baffeb !important; background: #0b2c2b !important; }
.tg-flow-item:nth-child(3) .tg-flow-badge { border-color: #9a8cff !important; color: #ddd8ff !important; background: #17152f !important; }
.tg-cta, .tg-cta-primary, .tg-cta-secondary {
  min-height: 68px !important; color: #d9faff !important;
  background: #0b1a29 !important; border: 1px solid rgba(123,183,202,.34) !important;
  border-radius: 14px !important; box-shadow: inset 0 1px 0 rgba(255,255,255,.08), 0 12px 26px rgba(0,0,0,.28) !important;
}
.tg-cta-primary { border-left: 3px solid #54e6ff !important; }
.tg-cta-secondary { border-left: 3px solid #63f5c7 !important; }
.tg-cta::before { background: linear-gradient(105deg, transparent 20%, rgba(255,255,255,.16) 48%, transparent 72%) !important; }
.tg-cta:hover, .tg-cta-primary:hover, .tg-cta-secondary:hover {
  background: #10293a !important; border-color: rgba(84,230,255,.7) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.12), 0 18px 34px rgba(0,0,0,.38), 0 0 24px rgba(84,230,255,.14) !important;
}
.tg-cta .q-icon { color: #54e6ff !important; }
.tg-cta-secondary .q-icon { color: #63f5c7 !important; }
@media (max-width: 640px) {
  .tg-flow { display: grid !important; gap: 7px !important; }
  .tg-flow::before, .tg-flow::after { display: none !important; }
}
"""

# 最终材质覆盖：液态玻璃、粒子背景、统一按钮系统。
CSS += """
/* ---------- Liquid glass + particle field ---------- */
html, body { background-color: #040a12 !important; }
body {
  background-image:
    radial-gradient(circle at 12% 18%, rgba(84,230,255,.72) 0 1px, transparent 2px),
    radial-gradient(circle at 28% 72%, rgba(99,245,199,.58) 0 1px, transparent 2px),
    radial-gradient(circle at 48% 34%, rgba(180,220,255,.52) 0 1px, transparent 2px),
    radial-gradient(circle at 67% 82%, rgba(84,230,255,.65) 0 1px, transparent 2px),
    radial-gradient(circle at 86% 26%, rgba(99,245,199,.6) 0 1px, transparent 2px),
    radial-gradient(circle at 76% 58%, rgba(180,220,255,.4) 0 1px, transparent 2px),
    linear-gradient(rgba(84,230,255,.028) 1px, transparent 1px),
    linear-gradient(90deg, rgba(84,230,255,.028) 1px, transparent 1px),
    radial-gradient(ellipse at 20% 0%, rgba(0,173,255,.18), transparent 43%),
    radial-gradient(ellipse at 90% 20%, rgba(99,245,199,.08), transparent 34%),
    linear-gradient(135deg, #040a12, #071421 55%, #06101a) !important;
  background-size: 260px 220px, 330px 280px, 410px 320px, 290px 250px, 370px 300px, 500px 380px, 42px 42px, 42px 42px, auto, auto, auto !important;
  animation: tg-particles 18s linear infinite !important;
}
@keyframes tg-particles {
  0% { background-position: 0 0, 0 0, 0 0, 0 0, 0 0, 0 0, 0 0, 0 0; }
  50% { background-position: 32px -24px, -26px 30px, 22px 18px, -18px -28px, 28px 20px, -30px 16px, 0 18px, 18px 0; }
  100% { background-position: 64px -48px, -52px 60px, 44px 36px, -36px -56px, 56px 40px, -60px 32px, 0 36px, 36px 0; }
}
.tg-card, .tg-hero, .tg-status {
  background: linear-gradient(135deg, rgba(20,43,58,.48), rgba(7,20,32,.34)) !important;
  border: 1px solid rgba(182,235,246,.17) !important;
  box-shadow: 0 25px 80px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.13), inset 0 -1px 0 rgba(84,230,255,.08) !important;
  backdrop-filter: blur(24px) saturate(145%) !important;
  -webkit-backdrop-filter: blur(24px) saturate(145%) !important;
}
.tg-hero { background: linear-gradient(135deg, rgba(27,65,82,.52), rgba(7,22,36,.30)) !important; }
.tg-flow-item {
  background: linear-gradient(135deg, rgba(21,53,67,.42), rgba(5,19,31,.27)) !important;
  border-color: rgba(170,226,239,.18) !important;
  backdrop-filter: blur(18px) saturate(150%) !important;
  -webkit-backdrop-filter: blur(18px) saturate(150%) !important;
}
/* ---------- Unified button system ---------- */
.q-btn.tg-cta, .q-btn.tg-step {
  isolation: isolate !important; overflow: hidden !important;
  min-height: 62px !important; border-radius: 16px !important;
  color: #dffcff !important; background: rgba(15,39,52,.46) !important;
  border: 1px solid rgba(156,229,236,.34) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.18), inset 0 -10px 22px rgba(84,230,255,.035), 0 12px 28px rgba(0,0,0,.22) !important;
  backdrop-filter: blur(18px) saturate(160%) !important;
  -webkit-backdrop-filter: blur(18px) saturate(160%) !important;
  transition: transform .28s cubic-bezier(.22,1,.36,1), border-color .28s ease, box-shadow .28s ease, background .28s ease !important;
}
.q-btn.tg-cta::before, .q-btn.tg-step::before {
  content: "" !important; position: absolute !important; inset: -2px !important; z-index: -1 !important;
  background: linear-gradient(110deg, transparent 22%, rgba(222,255,255,.34) 47%, transparent 70%) !important;
  transform: translateX(-130%) !important; transition: transform .9s cubic-bezier(.16,1,.3,1) !important;
}
.q-btn.tg-cta::after, .q-btn.tg-step::after {
  content: "" !important; position: absolute !important; inset: 1px !important; z-index: -1 !important;
  border-radius: 15px !important; border: 1px solid rgba(255,255,255,.08) !important; pointer-events: none !important;
}
.q-btn.tg-cta-primary { border-left: 2px solid #54e6ff !important; }
.q-btn.tg-cta-secondary { border-left: 2px solid #63f5c7 !important; }
.q-btn.tg-cta:hover, .q-btn.tg-step:hover {
  transform: translateY(-4px) !important;
  background: rgba(31,76,88,.58) !important;
  border-color: rgba(178,250,248,.72) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.24), inset 0 -12px 25px rgba(84,230,255,.07), 0 20px 38px rgba(0,0,0,.32), 0 0 24px rgba(99,245,199,.12) !important;
}
.q-btn.tg-cta:hover::before, .q-btn.tg-step:hover::before { transform: translateX(130%) !important; }
.q-btn.tg-cta:active, .q-btn.tg-step:active { transform: translateY(0) scale(.975) !important; }
.q-btn.tg-cta .q-icon, .q-btn.tg-step .q-icon { color: #8ff8f1 !important; filter: drop-shadow(0 0 7px rgba(99,245,199,.42)); }
@media (max-width: 640px) {
  .q-btn.tg-cta, .q-btn.tg-step { min-height: 58px !important; }
}
"""

PARTICLE_JS = """
<script>
(function () {
  if (!document.body) { setTimeout(arguments.callee, 50); return; }
  if (document.getElementById('tg-particles')) return;
  const canvas = document.createElement('canvas');
  canvas.id = 'tg-particles';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const ctx = canvas.getContext('2d');
  const dots = [];
  let width = 0, height = 0, dpr = 1;
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth; height = window.innerHeight;
    canvas.width = width * dpr; canvas.height = height * dpr;
    canvas.style.width = width + 'px'; canvas.style.height = height + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    dots.length = 0;
    const count = Math.min(95, Math.max(42, Math.floor(width * height / 15000)));
    for (let i = 0; i < count; i++) dots.push({
      x: Math.random() * width, y: Math.random() * height,
      vx: (Math.random() - .5) * .18, vy: (Math.random() - .5) * .16,
      r: Math.random() * 1.5 + .35, a: Math.random() * .55 + .2,
      phase: Math.random() * Math.PI * 2
    });
  }
  function frame(t) {
    ctx.clearRect(0, 0, width, height);
    for (const p of dots) {
      p.x += p.vx; p.y += p.vy; p.phase += .018;
      if (p.x < -8) p.x = width + 8; if (p.x > width + 8) p.x = -8;
      if (p.y < -8) p.y = height + 8; if (p.y > height + 8) p.y = -8;
      const alpha = p.a * (.72 + Math.sin(p.phase) * .28);
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = Math.random() > .5 ? `rgba(238,250,255,${alpha})` : `rgba(190,239,229,${alpha})`;
      ctx.shadowBlur = 7; ctx.shadowColor = '#d8fff5'; ctx.fill(); ctx.shadowBlur = 0;
    }
    requestAnimationFrame(frame);
  }
  window.addEventListener('resize', resize, { passive: true });
  resize(); requestAnimationFrame(frame);
})();
</script>
"""

CSS += """
#tg-particles { position: fixed; inset: 0; z-index: 0; pointer-events: none; opacity: .72; }
.tg-brand, .tg-main { position: relative; z-index: 1; }
.q-btn.tg-deploy, .q-btn.tg-finish {
  position: relative !important; isolation: isolate !important; overflow: hidden !important;
  min-height: 68px !important; border-radius: 15px !important;
  color: #e7ffff !important; background: rgba(8,25,38,.62) !important;
  border: 1px solid rgba(148,226,232,.35) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.16), inset 0 -16px 28px rgba(84,230,255,.045), 0 14px 28px rgba(0,0,0,.26) !important;
  backdrop-filter: blur(20px) saturate(150%) !important;
  -webkit-backdrop-filter: blur(20px) saturate(150%) !important;
  transition: transform .25s ease, background .25s ease, border-color .25s ease, box-shadow .25s ease !important;
}
.q-btn.tg-deploy { border-left: 3px solid #54e6ff !important; }
.q-btn.tg-finish { border-left: 3px solid #63f5c7 !important; }
.q-btn.tg-deploy::before, .q-btn.tg-finish::before {
  content: ""; position: absolute; inset: 0; z-index: -1; pointer-events: none;
  background: linear-gradient(105deg, transparent 18%, rgba(220,255,255,.25) 48%, transparent 72%);
  transform: translateX(-125%); transition: transform .8s cubic-bezier(.16,1,.3,1);
}
.q-btn.tg-deploy:hover, .q-btn.tg-finish:hover {
  transform: translateY(-4px) !important; background: rgba(22,61,72,.72) !important;
  border-color: rgba(190,255,250,.72) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.25), 0 20px 38px rgba(0,0,0,.38), 0 0 28px rgba(84,230,255,.16) !important;
}
.q-btn.tg-deploy:hover::before, .q-btn.tg-finish:hover::before { transform: translateX(125%); }
.q-btn.tg-deploy:active, .q-btn.tg-finish:active { transform: scale(.975) !important; }
.q-btn.tg-deploy .q-icon { color: #54e6ff !important; filter: drop-shadow(0 0 8px rgba(84,230,255,.7)); }
.q-btn.tg-finish .q-icon { color: #63f5c7 !important; filter: drop-shadow(0 0 8px rgba(99,245,199,.7)); }
"""

CSS += """
/* Final cleanup: neutral glass controls and static connector */
.tg-flow::before { background: linear-gradient(90deg, transparent, rgba(210,230,232,.55), rgba(99,245,199,.7), rgba(210,230,232,.55), transparent) !important; animation: none !important; box-shadow: 0 0 9px rgba(165,220,216,.25) !important; }
.tg-flow::after { display: none !important; animation: none !important; }
.tg-flow-badge, .tg-flow-item:nth-child(2) .tg-flow-badge, .tg-flow-item:nth-child(3) .tg-flow-badge {
  background: rgba(34,52,60,.76) !important; border-color: rgba(198,232,232,.62) !important;
  color: #e6f4f2 !important; box-shadow: 0 0 0 4px rgba(6,16,25,.88), 0 0 14px rgba(152,220,211,.18) !important;
}
.q-btn.tg-deploy, .q-btn.tg-finish {
  color: #e5efef !important; background: rgba(27,40,46,.58) !important;
  border: 1px solid rgba(189,215,216,.34) !important; border-left: 1px solid rgba(189,215,216,.34) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.15), inset 0 -14px 24px rgba(180,220,216,.035), 0 12px 26px rgba(0,0,0,.24) !important;
}
.q-btn.tg-deploy:hover, .q-btn.tg-finish:hover {
  background: rgba(48,64,67,.72) !important; border-color: rgba(219,242,237,.68) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.22), 0 18px 34px rgba(0,0,0,.32), 0 0 22px rgba(180,220,216,.12) !important;
}
.q-btn.tg-deploy .q-icon, .q-btn.tg-finish .q-icon { color: #c7dfdc !important; filter: drop-shadow(0 0 6px rgba(205,237,232,.35)) !important; }
"""

# 复制函数：http 下 navigator.clipboard 不可用，必须用 execCommand 回退
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
    ui.add_head_html(PARTICLE_JS)
    ui.add_head_html(COPY_JS)
    ui.add_head_html(ENTER_JS)


def _fmt(r: dict) -> str:
    res = r["result"]
    if res["ok"]:
        return f"{res['ms']} ms"
    return f"不可用（{res.get('err') or res.get('status')}）"


def _diagnose_failure(output: list[str], fallback: str) -> tuple[str, str, str]:
    text = "\n".join(output[-120:])
    rules = (
        (("no space left", "disk quota exceeded"), "磁盘空间不足", "清理无用镜像、容器日志或扩容磁盘后重试。"),
        (("connection timed out", "i/o timeout", "TLS handshake timeout"), "网络连接超时", "检查 VPS 出站网络；若镜像层 CDN 不通，使用离线镜像上传导入。"),
        (("no such file or directory", "test -d", "cannot stat"), "所需文件或目录不存在", "确认面板源码包包含对应目录，并检查安装路径和文件权限。"),
        (("permission denied", "operation not permitted"), "权限不足", "检查面板运行用户对目标目录、Docker socket 和系统服务的权限。"),
        (("address already in use", "port is already allocated", "bind: address"), "端口已被占用", "检查占用进程并释放端口，或调整服务端口映射。"),
        (("unauthorized", "authentication required", "denied: requested access"), "镜像仓库认证失败或无权访问", "核对镜像名称、标签及仓库凭据；公开镜像仍失败时检查镜像源。"),
        (("manifest unknown", "not found: manifest"), "镜像或标签不存在", "核对镜像仓库地址和标签，使用该项目实际发布的标签。"),
        (("could not resolve", "temporary failure in name resolution", "no such host"), "DNS 解析失败", "检查 VPS DNS 与出站策略，确认目标域名可解析。"),
        (("dpkg was interrupted", "unmet dependencies", "unable to correct problems"), "系统软件包安装失败", "按日志修复 apt/dpkg 状态后重试，避免并行运行系统更新。"),
        (("yaml", "compose config", "invalid compose"), "Compose 配置无效", "检查 YAML 缩进、必填环境变量和 Docker Compose 版本。"),
    )
    lowered = text.lower()
    for needles, reason, solution in rules:
        if any(needle in lowered for needle in needles):
            break
    else:
        reason = fallback
        solution = "查看日志中首个报错及其前后内容；当前特征未匹配到已知故障类型。"
    error_lines = [line.strip() for line in output if line.strip() and ("error" in line.lower() or "failed" in line.lower() or "失败" in line or "denied" in line.lower() or "timeout" in line.lower() or "timed out" in line.lower() or "not found" in line.lower() or "refused" in line.lower())]
    detail = error_lines[-1] if error_lines else (output[-2].strip() if len(output) > 1 else (output[-1].strip() if output else "无命令输出"))
    return reason, solution, detail[:500]

def _set_task(status: str, stage: str = "", progress: float | None = None) -> None:
    DEPLOY_VIEW["status"] = status
    DEPLOY_VIEW["stage"] = stage
    DEPLOY_VIEW["progress"] = progress
    if DEPLOY_VIEW.get("status_label"):
        DEPLOY_VIEW["status_label"].text = status
        DEPLOY_VIEW["stage_label"].text = stage
        if progress is None:
            DEPLOY_VIEW["progress_bar"].visible = False
            DEPLOY_VIEW["percent_label"].text = ""
        else:
            percent = max(0, min(100, round(progress * 100)))
            DEPLOY_VIEW["progress_bar"].visible = True
            DEPLOY_VIEW["progress_bar"].value = percent / 100
            DEPLOY_VIEW["percent_label"].text = f"{percent}%"
        DEPLOY_VIEW["status_label"].update()
        DEPLOY_VIEW["stage_label"].update()
        DEPLOY_VIEW["progress_bar"].update()
        DEPLOY_VIEW["percent_label"].update()
async def _run_tracked(cmds: list) -> tuple[int, list[str]]:
    output = []
    def record(line: str) -> None:
        output.append(line)
        LOG.push(line)
    code = await run_stream_all(cmds, record)
    return code, output

def _show_failure(title: str, output: list[str], fallback: str) -> tuple[str, str, str]:
    reason, solution, detail = _diagnose_failure(output, fallback)
    stage = f"{title}。原因：{reason}。建议：{solution}。日志：{detail}"
    _set_task("执行失败", stage)
    ui.notify(f"{title}失败：{reason}。{solution}", type="negative", timeout=12000)
    return reason, solution, detail

def _guard() -> bool:
    if STATE["busy"]:
        ui.notify("有任务正在执行，请等它结束。", type="warning")
        return False
    STATE["busy"] = True
    _set_task("任务已开始", "准备执行", 0)
    ui.notify("任务已开始", type="info")
    return True
async def _run(title: str, cmds: list):
    _set_task("正在执行", title)
    LOG.push(f"===== {title} =====")
    output = []
    try:
        code, output = await _run_tracked(cmds)
        if code == 0:
            _set_task("已完成", title, 1)
            ui.notify(f"{title}完成", type="positive")
        else:
            _show_failure(title, output, f"命令执行失败，退出码 {code}")
    except Exception as exc:
        _show_failure(title, output, f"任务异常中止：{exc}")
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

async def _open_post_setup():
    with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
        ui.label("扫码登录后完成设置").classes("text-lg font-semibold")
        ui.label("请输入当前 AstrBot 控制台密码。密码只用于本次设置，不会保存。")
        password_input = ui.input("AstrBot 密码", password=True, password_toggle_button=True).props("autofocus").classes("w-full")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("取消", on_click=dialog.close).props("flat")
            async def submit():
                dialog.close()
                await _post_login_setup(password_input.value or "")
            ui.button("开始设置", icon="settings", on_click=submit).props("color=primary")
    dialog.open()

async def _post_login_setup(password: str):
    if not _guard():
        return
    _set_task("正在执行", "扫码登录后配置 AstrBot", 0)
    LOG.push("===== 扫码登录后配置开始 =====")
    try:
        message = await setup_after_qq_login(password)
        _set_task("已完成", message, 1)
        LOG.push(message)
        ui.notify(message, type="positive")
    except Exception as exc:
        _show_failure("扫码登录后配置", [str(exc)], "请确认已扫码登录 QQ，且 AstrBot 正常运行")
    finally:
        STATE["busy"] = False
        LOG.push("===== 扫码登录后配置结束 =====")

async def _auto_deploy():
    """真小白主流程：体检、Docker、源、AstrBot、SnowLuma、插件。"""
    if not _guard():
        return
    LOG.push("===== 一键自动部署开始 =====")
    # 七个阶段的顺序固定，进度按阶段编号更新。
    try:
        for index, (title, cmds) in enumerate((("环境体检", CHECK_CMDS), ("安装 Docker", DOCKER_CMDS)), start=1):
            _set_task("正在执行", f"阶段 {index}/7：{title}", (index - 1) / 7)
            LOG.push(f"--- {title} ---")
            code, output = await _run_tracked(cmds)
            if code != 0:
                _show_failure(title, output, f"命令执行失败，退出码 {code}")
                return

        _set_task("正在执行", "阶段 3/7：检测并应用镜像源", 2 / 7)
        LOG.push("--- 自动测速并应用 Docker 镜像源 ---")
        results = await sources.test_all(sources.DOCKER_MIRRORS, sources.docker_mirror_url)
        best = sources.pick_best(results)
        if not best:
            raise RuntimeError("没有可用的 Docker 镜像源；请更换服务器线路，或准备代理/镜像中转")
        STATE["mirror"] = best
        LOG.push(f"自动选中：{best['name']}（{best['result'].get('ms')} ms）")
        code, output = await _run_tracked(apply_mirror_cmds(best["url"]))
        if code != 0:
            _show_failure("镜像源应用", output, f"命令执行失败，退出码 {code}")
            return

        image_title = "准备组件" if bundle_configured() else "检查组件镜像"
        _set_task("正在执行", f"阶段 4/7：{image_title}", 3 / 7)
        LOG.push(f"--- {image_title} ---")
        code, output = await _run_tracked(image_prepare_cmds())
        if code != 0:
            _show_failure(image_title, output, "组件镜像尚未准备好")
            return

        deploy_stages = [
            ("安装 AstrBot", ASTRBOT_CMDS),
            ("安装 SnowLuma", snowluma_cmds(STATE["proxy"]["prefix"] if STATE["proxy"] else "")),
            ("装配套插件", PLUGIN_INSTALL_CMDS),
        ]
        for index, (title, cmds) in enumerate(deploy_stages, start=5):
            _set_task("正在执行", f"阶段 {index}/7：{title}", (index - 1) / 7)
            LOG.push(f"--- {title} ---")
            code, output = await _run_tracked(cmds)
            if code != 0:
                _show_failure(title, output, f"命令执行失败，退出码 {code}")
                return

        _set_task("部署完成", "七个阶段全部完成", 1)
        LOG.push("===== 一键自动部署完成 =====")
        ui.notify("自动部署完成，请查看凭据并按教程登录 QQ", type="positive")
    except Exception as exc:
        reason, solution, detail = _diagnose_failure([str(exc)], "自动部署中断")
        _set_task("部署失败", f"原因：{reason}。建议：{solution}。详情：{detail}")
        LOG.push(f"!! 原因：{reason}。建议：{solution}。详情：{detail}")
        ui.notify(f"自动部署失败：{reason}。{solution}", type="negative", timeout=12000)
    finally:
        STATE["busy"] = False
        LOG.push("===== 一键自动部署结束 =====")

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
        "<th>服务</th><th>用户名</th><th>端口</th><th>密码说明</th><th></th>",
        "</tr></thead><tbody>",
    ]
    for r in rows:
        name = _html.escape(r["name"])
        username = _html.escape(r.get("username", "")) or "—"
        if r["ok"]:
            if r.get("key") == "astrbot":
                pw = "请在第二步输入当前密码"
                quoted = ""
            else:
                pw = _html.escape(r["value"])
                quoted = json.dumps(r["value"])  # 安全地嵌入 onclick
            out.append(
                f"<tr><td>{name}</td>"
                f"<td>{username}</td>"
                f'<td class="tg-port">{r["port"]}</td>'
                f'<td class="tg-pw">{pw}</td>'
                + (f'<td><button class="tg-copy" onclick=\'tgCopy(this, {quoted})\'>复制</button></td></tr>' if quoted else '<td></td></tr>')
            )
        else:
            out.append(
                f"<tr><td>{name}</td>"
                f"<td>{username}</td>"
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


def offline_image_section():
    ui.markdown(
        "网络线路无法下载镜像分层时，在可联网的 Docker 电脑执行对应命令导出镜像：\n\n"
        "SnowLuma：`docker save -o snowluma.tar motricseven7/snowluma:latest`\n\n"
        "AstrBot：`docker save -o astrbot.tar soulter/astrbot:latest`\n\n"
        "把 tar 包上传后，选择对应镜像再点击导入。导入成功后重新点击自动部署。"
    )
    image_choice = ui.select(offline.IMAGE_OPTIONS, value=offline.DEFAULT_IMAGE, label="要导入的镜像").classes("w-full max-w-md")
    status = ui.column().classes("w-full")
    packages = ui.column().classes("w-full")

    async def refresh_packages():
        packages.clear()
        with packages:
            items = offline.list_packages()
            if not items:
                ui.label("尚无已上传的镜像包。").classes("text-sm opacity-60")
            for package in items:
                size_mb = package.stat().st_size / (1024 * 1024)
                with ui.row().classes("items-center gap-2 w-full"):
                    ui.label(f"{package.name} · {size_mb:.1f} MiB").classes("text-sm")
                    async def import_package(path=package):
                        if not _guard():
                            return
                        await _run(f"导入离线镜像：{path.name}", offline.import_cmds(path, image_choice.value))
                    ui.button("导入并检查", icon="inventory_2", on_click=import_package).classes("tg-step")

    async def receive_upload(event):
        try:
            filename = offline.safe_upload_name(event.name)
            offline.ensure_upload_dir()
            target = offline.unique_upload_path(filename)
            size = 0
            with target.open("wb") as output:
                while chunk := await event.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > offline.MAX_PACKAGE_BYTES:
                        output.close()
                        target.unlink(missing_ok=True)
                        raise ValueError("文件超过 30 GiB 上限")
                    output.write(chunk)
            if size == 0:
                target.unlink(missing_ok=True)
                raise ValueError("上传文件为空")
            status.clear()
            with status:
                ui.label(f"已接收 {filename}（{size / (1024 * 1024):.1f} MiB）").classes("text-positive")
        except Exception as exc:
            status.clear()
            with status:
                ui.label(f"上传失败：{exc}").classes("text-negative")
        await refresh_packages()

    ui.upload(on_upload=receive_upload, auto_upload=True, max_file_size=offline.MAX_PACKAGE_BYTES).props(
        "accept=.tar,.gz multiple=false"
    ).classes("w-full")
    ui.label("支持 Docker 导出的 .tar、.tar.gz、.tgz；单文件最大 30 GiB。上传后仍需点击导入。").classes("text-xs opacity-60")
    status
    packages
    ui.timer(0.1, refresh_packages, once=True)


def credential_section():
    ui.markdown(
        "这里显示的是登录信息。AstrBot 的密码以你**当前实际密码**为准；"
        "修改密码后，刷新本表不会改变密码。第二步设置时会再次要求输入当前密码。"
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
    ui.label("打开 noVNC").classes("text-sm font-semibold mt-4 opacity-80")
    ui.html(
        '<div class="tg-nat">'
        '<strong>端口提示</strong>'
        '<span><small>独立公网服务器填 <b>6081</b>。</small>'
        '<small>NAT 服务器填服务商分配的外部端口，不要直接填内部端口 6081。</small>'
        '<small>如果服务商没有把外部端口映射到内部 6081，noVNC 无法打开。</small></span>'
        '</div>', sanitize=False
    )
    with ui.row().classes("w-full items-end gap-2"):
        novnc_port = ui.input("noVNC 外部端口", value="6081").props("type=number min=1 max=65535").classes("flex-1")
        async def open_novnc():
            try:
                port = int(str(novnc_port.value or "").strip())
                if not 1 <= port <= 65535:
                    raise ValueError
            except ValueError:
                ui.notify("请输入有效的外部端口", type="warning")
                return
            await ui.run_javascript(
                "window.open('http://' + window.location.hostname + ':' + %d + '/vnc.html?autoconnect=1', '_blank')" % port
            )
        ui.button("打开 noVNC", icon="open_in_new", on_click=open_novnc).classes("tg-step")
    ui.label("各服务的内部端口").classes("text-sm font-semibold mt-4 opacity-80")
    ui.html(_port_table_html(), sanitize=False)


# ---------------------------------------------------------------- 首页

async def _logout() -> None:
    # 清 Cookie 必须由服务端做，所以整页跳转；不能用 SPA 路由（那不会发请求）
    await ui.run_javascript("window.location.href = '/logout';")


def _brand_bar(admin: bool = False) -> None:
    with ui.row().classes("tg-brand w-full items-center gap-3 px-5 py-4 no-wrap"):
        ui.html(LOGO_SVG, sanitize=False)
        with ui.column().classes("gap-0"):
            ui.label("图恒宇计划").classes("tg-title")
            ui.label("安装向导" if not admin else "管理工具").classes("tg-sub")
        ui.space()
        if admin:
            ui.link("返回安装页", "/").classes("text-sm")
        ui.button(icon="logout", on_click=_logout).props("flat round dense").tooltip("退出登录")

@ui.page("/")
def index():
    global LOG
    apply_style()
    LOG = ui.log(max_lines=4000).classes("hidden")
    _brand_bar()
    with ui.column().classes("tg-main w-full max-w-2xl mx-auto gap-4 p-4"):
        with ui.card().classes("tg-card tg-hero w-full"):
            ui.label("QQ 机器人部署向导").classes("tg-kicker")
            ui.label("把服务器变成你的机器人").classes("text-2xl font-semibold mt-1")
            ui.label("按顺序完成下面三步。面板会处理安装、连接和配置。你只需要扫码，并输入当前 AstrBot 密码。").classes("text-sm opacity-75 mt-1")
            ui.html(
                '<div class="tg-flow">'
                '<div class="tg-flow-item"><span class="tg-flow-badge">1</span><span class="tg-flow-text">部署必要软件</span></div>'
                '<div class="tg-flow-item"><span class="tg-flow-badge">2</span><span class="tg-flow-text">noVNC 扫码登录 QQ</span></div>'
                '<div class="tg-flow-item"><span class="tg-flow-badge">3</span><span class="tg-flow-text">输入密码完成设置</span></div>'
                '</div>', sanitize=False
            )
            with ui.row().classes("w-full gap-2"):
                ui.button("1. 部署必要软件", icon="rocket_launch", on_click=_auto_deploy).props("unelevated no-caps").classes("tg-deploy flex-1")
                ui.button("2. 扫码后完成设置", icon="settings", on_click=_open_post_setup).props("unelevated no-caps").classes("tg-finish flex-1")
            ui.html(
                '<div class="tg-nat">'
                '<strong>⚠ NAT 用户先看</strong>'
                '<span><small>面板端口、noVNC 端口都要使用服务商分配的外部端口。</small>'
                '<small>noVNC 默认填 <b>6081</b> 仅适用于独立公网服务器；NAT 请填映射到内部 <b>6081</b> 的外部端口。</small></span>'
                '</div>', sanitize=False
            )
        with ui.card().classes("tg-card tg-status w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("安装状态").classes("text-sm font-semibold opacity-70")
                with ui.row().classes("items-center gap-2"):
                    status_label = ui.label(DEPLOY_VIEW.get("status") or "等待开始").classes("text-sm font-semibold")
                    percent_label = ui.label("").classes("tg-status-percent text-sm font-bold")
            stage_label = ui.label(DEPLOY_VIEW.get("stage") or "点击上方按钮开始").classes("text-sm opacity-75 mt-2")
            progress_bar = ui.linear_progress(value=DEPLOY_VIEW.get("progress") or 0).classes("w-full mt-3")
            DEPLOY_VIEW["percent_label"] = percent_label
            DEPLOY_VIEW["status_label"] = status_label
            DEPLOY_VIEW["stage_label"] = stage_label
            DEPLOY_VIEW["progress_bar"] = progress_bar
            if DEPLOY_VIEW.get("progress") is None:
                progress_bar.visible = False
            else:
                percent_label.text = f"{round(DEPLOY_VIEW['progress'] * 100)}%"
        with ui.expansion("第 1 步完成后：扫码登录 QQ", icon="qr_code_scanner", value=False).classes("tg-card w-full"):
            ui.label("先完成第一步，再读取 noVNC 地址和密码。在远程桌面中用手机 QQ 扫码登录，看到 QQ 主界面后再点击上面的第 2 步。")
            credential_section()
        ui.link("管理员工具", "/admin").classes("text-xs opacity-50")

@ui.page("/admin")
def admin_page():
    global LOG
    apply_style()
    _brand_bar(admin=True)
    with ui.column().classes("tg-main w-full max-w-5xl mx-auto gap-4 p-4"):
        with ui.expansion("单独重试安装步骤", icon="build", value=False).classes("tg-card w-full"):
            with ui.row().classes("gap-2 w-full"):
                ui.button("环境检查", icon="health_and_safety", on_click=_handler("环境检查", CHECK_CMDS)).classes("tg-step")
                ui.button("安装 Docker", icon="inventory_2", on_click=_handler("安装 Docker", DOCKER_CMDS)).classes("tg-step")
                ui.button("安装 SnowLuma", icon="chat", on_click=_dynamic_handler("安装 SnowLuma", lambda: snowluma_cmds(STATE["proxy"]["prefix"] if STATE["proxy"] else ""))).classes("tg-step")
                ui.button("安装 AstrBot", icon="smart_toy", on_click=_handler("安装 AstrBot", ASTRBOT_CMDS)).classes("tg-step")
                ui.button("安装插件", icon="extension", on_click=_handler("装配套插件", PLUGIN_INSTALL_CMDS)).classes("tg-step")
        with ui.expansion("镜像下载线路", icon="tune", value=False).classes("tg-card w-full"):
            source_section()
        with ui.expansion("管理员离线镜像导入", icon="upload_file", value=False).classes("tg-card w-full"):
            offline_image_section()
        with ui.card().classes("tg-card w-full"):
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