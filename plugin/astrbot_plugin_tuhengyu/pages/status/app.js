// 图恒宇 · 运行状态页面
// 通过 AstrBot 注入的 window.AstrBotPluginPage bridge 与插件后端通信。
//   apiGet("status")        -> /api/v1/plugins/extensions/astrbot_plugin_tuhengyu/status
//   apiPost("reschedule")   -> …/reschedule
//   apiPost("test-moment")  -> …/test-moment

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
    const awake = $("awake");
    if (awake) {
      awake.textContent = DASH;
      awake.classList.remove("on");
    }
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

  // 人设 / 作息模式：决定「重算作息」按钮会得到什么
  if (data.persona_set) {
    text("persona-state", "人设已填");
  } else {
    text("persona-state", "人设未填");
  }
  const warn = $("reschedule-warn");
  if (warn) {
    if (!data.persona_set) {
      warn.hidden = false;
      warn.textContent =
        "当前 persona_prompt 为空，点「重算作息」只会得到保守默认（09:00–23:00 醒、场景「在家待着 · 闲着」）。先去插件配置里填人设。";
    } else if (!data.schedule_auto) {
      warn.hidden = false;
      warn.textContent =
        "schedule.auto_generate 已关，作息走手填 manual_hours，点「重算作息」不会让模型生成。";
    } else {
      warn.hidden = true;
      warn.textContent = "";
    }
  }

  const prob = Number(data.effective_probability);
  text("prob", Number.isFinite(prob) ? `${(prob * 100).toFixed(1)}%` : DASH);
  text(
    "prob-detail",
    data.state_bias_on
      ? `基准 ${data.act_probability} × 状态 ${data.bias_factor}`
      : `基准 ${data.act_probability}（状态加权已关）`,
  );

  text("interval", `${data.check_interval_minutes ?? DASH} 分钟`);
  text("moment", data.moment_enabled ? "开" : "关");
  text("moment-detail", `最短间隔 ${data.moment_min_interval_hours ?? DASH} 小时`);
  text("last-moment", data.last_moment ?? "无");

  renderPeriods(data.periods);
}

function renderTestResult(result) {
  const node = $("test-result");
  if (!node) return;
  if (!result) {
    node.hidden = true;
    return;
  }
  node.hidden = false;
  node.classList.toggle("err", !result.ok);
  if (result.ok) {
    node.textContent = `已发布（此刻：${result.state ?? DASH}）：${result.content ?? ""}`;
  } else if (result.content) {
    node.textContent = `生成成功但发布失败：${result.message ?? ""}（内容：${result.content}）`;
  } else {
    node.textContent = result.message || "发布失败。";
  }
}

async function refresh() {
  try {
    const data = await bridge.apiGet("status");
    render(data);
  } catch (e) {
    showNotice(`读取状态失败：${e.message}`, true);
  }
}

async function withButton(id, busyLabel, fn) {
  const btn = $(id);
  if (btn) btn.disabled = true;
  showNotice(busyLabel);
  try {
    await fn();
  } finally {
    if (btn) btn.disabled = false;
  }
}

function reschedule() {
  return withButton("reschedule", "正在重算作息（读人设 → 问模型 → 存盘）……", async () => {
    try {
      const data = await bridge.apiPost("reschedule", {});
      render(data);
      if (data.persona_set) {
        showNotice("作息已重算。");
      } else {
        showNotice("已重算，但人设为空，结果是保守默认。", true);
      }
    } catch (e) {
      showNotice(`重算失败：${e.message}`, true);
    }
  });
}

function testMoment() {
  const ok = window.confirm("这会真的往 QQ 空间发一条动态。确定要继续吗？");
  if (!ok) return;
  return withButton("test-moment", "正在生成并发布，稍等……", async () => {
    try {
      const data = await bridge.apiPost("test-moment", {});
      render(data);
      renderTestResult(data.result);
      showNotice(data.result?.ok ? "" : "发布未成功，看下面结果。");
    } catch (e) {
      showNotice(`发布失败：${e.message}`, true);
    }
  });
}

function bind() {
  $("refresh")?.addEventListener("click", refresh);
  $("reschedule")?.addEventListener("click", reschedule);
  $("test-moment")?.addEventListener("click", testMoment);
  bridge.onContext?.(() => {
    document.title = bridge.t?.("pages.status.title", "图恒宇 · 运行状态") ?? document.title;
  });
}

bind();
refresh();
setInterval(refresh, 30000);
