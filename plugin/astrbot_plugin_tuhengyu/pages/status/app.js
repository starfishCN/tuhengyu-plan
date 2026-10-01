// 图恒宇 · 运行状态页面
// 通过 AstrBot 注入的 window.AstrBotPluginPage bridge 与插件后端通信。
// apiGet("status") -> /api/v1/plugins/extensions/astrbot_plugin_tuhengyu/status

const bridge = window.AstrBotPluginPage;

const $ = (id) => document.getElementById(id);
const DASH = "—";

function text(id, value) {
  const node = $(id);
  if (node) node.textContent = (value === null || value === undefined || value === "") ? DASH : String(value);
}

function toMinutes(hhmm) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || "").trim());
  if (!m) return null;
  return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
}

function hitNow(start, end, nowMin) {
  const a = toMinutes(start);
  const b = toMinutes(end);
  if (a === null || b === null || nowMin === null) return false;
  return a <= b ? (nowMin >= a && nowMin <= b) : (nowMin >= a || nowMin <= b);
}

function showNotice(message, isError) {
  const node = $("notice");
  if (!node) return;
  if (!message) {
    node.hidden = true;
    node.textContent = "";
    return;
  }
  node.hidden = false;
  node.textContent = message;
  node.classList.toggle("err", !!isError);
}

function renderPeriods(periods) {
  const body = $("periods");
  if (!body) return;
  const list = Array.isArray(periods) ? periods : [];
  if (!list.length) {
    body.innerHTML = '<tr><td colspan="4" class="empty">暂无时段</td></tr>';
    return;
  }
  const now = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();
  body.innerHTML = "";
  for (const p of list) {
    const tr = document.createElement("tr");
    if (hitNow(p.start, p.end, nowMin)) tr.className = "period-now";
    const cells = [
      `${p.start ?? DASH} ~ ${p.end ?? DASH}`,
      p.scene ?? DASH,
      p.state ?? DASH,
      p.awake ? "是" : "否",
    ];
    for (const value of cells) {
      const td = document.createElement("td");
      td.textContent = String(value);
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

function render(data) {
  if (!data || data.running === false) {
    text("scene", "调度器未运行");
    text("awake", "");
    $("awake")?.classList.remove("on");
    showNotice("插件可能被禁用，或尚未加载完成。", true);
    return;
  }
  showNotice("");

  text("scene", `${data.scene ?? DASH} · ${data.state ?? DASH}`);
  const awake = $("awake");
  if (awake) {
    awake.textContent = data.awake ? "醒着" : "睡着";
    awake.classList.toggle("on", !!data.awake);
  }
  text("source", data.source ?? DASH);
  text("schedule-desc", data.schedule_desc ?? DASH);
  text("clock", data.now ?? DASH);

  const prob = Number(data.effective_probability);
  text("prob", Number.isFinite(prob) ? `${(prob * 100).toFixed(1)}%` : DASH);
  if (data.state_bias_on) {
    text("prob-detail", `基准 ${data.act_probability} × 状态 ${data.bias_factor}`);
  } else {
    text("prob-detail", `基准 ${data.act_probability}（状态加权已关）`);
  }

  text("interval", `${data.check_interval_minutes ?? DASH} 分钟`);

  text("moment", data.moment_enabled ? "开" : "关");
  text("moment-detail", `最短间隔 ${data.moment_min_interval_hours ?? DASH} 小时`);

  text("last-moment", data.last_moment ?? "无");

  renderPeriods(data.periods);
}

async function refresh() {
  try {
    const data = await bridge.apiGet("status");
    render(data);
  } catch (e) {
    showNotice(`读取状态失败：${e.message}`, true);
  }
}

async function reschedule() {
  const btn = $("reschedule");
  if (btn) btn.disabled = true;
  showNotice("正在重算作息 ……");
  try {
    const data = await bridge.apiPost("reschedule", {});
    render(data);
    showNotice("作息已重算。");
  } catch (e) {
    showNotice(`重算失败：${e.message}`, true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function bind() {
  $("refresh")?.addEventListener("click", refresh);
  $("reschedule")?.addEventListener("click", reschedule);
  // 响应 WebUI 语言切换，保持标题一致。
  bridge.onContext?.(() => {
    document.title = bridge.t?.("pages.status.title", "图恒宇 · 运行状态") ?? document.title;
  });
}

bind();
refresh();
// 每 30 秒自动刷新一次时钟与状态。
setInterval(refresh, 30000);