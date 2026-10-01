// 图恒宇 · 控制台页面（状态 / 操作 / 设置 三页签）
// 经 AstrBot 注入的 window.AstrBotPluginPage bridge 与后端通信：
//   apiGet("status")          读取运行状态
//   apiPost("reschedule")     重算作息
//   apiPost("test-moment")    立即发一条空间动态
//   apiPost("sticker-reload") 重扫表情包目录
//   apiGet("settings")        读设置（schema + 当前值 + 下拉选项）
//   apiPost("settings")       保存设置

const bridge = window.AstrBotPluginPage;

const $ = (id) => document.getElementById(id);
const DASH = "—";

function text(id, value) {
  const node = $(id);
  if (node) {
    node.textContent =
      value === null || value === undefined || value === "" ? DASH : String(value);
  }
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => {
    const code = c.charCodeAt(0);
    if (code === 38) return "&" + "amp;";
    if (code === 60) return "&" + "lt;";
    if (code === 62) return "&" + "gt;";
    if (code === 34) return "&" + "quot;";
    return "&" + "#39;";
  });
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
  return a <= b ? nowMin >= a && nowMin <= b : nowMin >= a || nowMin <= b;
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

  if (data.persona_set) {
    text("persona-state", data.persona_label || "已设置");
  } else {
    text("persona-state", "未检测到");
  }
  const note = $("persona-note");
  if (note) {
    let msg = "";
    if (!data.persona_set) {
      msg =
        "没读到人设。去 AstrBot 的「人格」里配一个，或在「设置」页的「人格」下拉里指定；都为空时作息只会得到保守默认。";
    } else if (data.schedule_error) {
      msg = `作息没能按人设生成（${data.schedule_error}）。常见原因：AstrBot 里没有可用的对话模型，或模型调用报错 —— 看日志里的 [图恒宇] 行。`;
    } else if (data.persona_pending) {
      msg = "检测到人设与盘上的作息对不上（换过人格），去「操作」页点「重算作息」。";
    }
    note.hidden = !msg;
    note.textContent = msg;
  }
  const warn = $("reschedule-warn");
  if (warn) {
    if (!data.persona_set) {
      warn.hidden = false;
      warn.textContent =
        "当前没有可用人设，点「重算作息」只会得到保守默认（09:00–23:00 醒、场景「在家待着 · 闲着」）。先去 AstrBot 里配人格，或在「设置」页里选。";
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

  text("sticker", data.sticker_enabled ? "开" : "关");
  const sp = Number(data.sticker_probability);
  text(
    "sticker-detail",
    `${data.sticker_desc ?? DASH}（每条 ${Number.isFinite(sp) ? (sp * 100).toFixed(0) : DASH}%）`,
  );

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

// ==================== 页签 ====================

function switchTab(name) {
  for (const b of document.querySelectorAll(".tab")) {
    b.classList.toggle("active", b.dataset.tab === name);
  }
  for (const p of document.querySelectorAll(".tab-pane")) {
    p.classList.toggle("active", p.id === "pane-" + name);
  }
  if (name === "stickers") loadStickers();
}

function setupTabs() {
  const nav = $("tabs");
  if (!nav) return;
  nav.addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (btn) switchTab(btn.dataset.tab);
  });
}

// ==================== 表情包库 ====================

const STICKER_MIME = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".bmp": "image/bmp",
};

function mimeOf(name) {
  const s = String(name || "");
  const i = s.lastIndexOf(".");
  const ext = i >= 0 ? s.slice(i).toLowerCase() : "";
  return STICKER_MIME[ext] || "image/png";
}

function fmtSize(n) {
  const v = Number(n) || 0;
  if (v >= 1024 * 1024) return (v / 1024 / 1024).toFixed(1) + " MB";
  if (v >= 1024) return (v / 1024).toFixed(0) + " KB";
  return v + " B";
}

function stickerCard(img) {
  const card = document.createElement("figure");
  card.className = "sticker-card";
  if (img.b64) {
    const el = document.createElement("img");
    el.loading = "lazy";
    el.alt = img.name;
    el.src = "data:" + mimeOf(img.name) + ";base64," + img.b64;
    card.appendChild(el);
  } else {
    const ph = document.createElement("div");
    ph.className = "sticker-ph";
    ph.textContent = img.skipped ? "过大，未预览" : img.error || "无法预览";
    card.appendChild(ph);
  }
  const cap = document.createElement("figcaption");
  let label = img.name + " · " + fmtSize(img.size);
  if (img.thumb) label += " · 缩略";
  cap.textContent = label;
  card.appendChild(cap);
  return card;
}

function renderStickers(data) {
  const box = $("sticker-gallery");
  if (!box) return;
  const groups = (data && data.groups) || [];
  const sum = $("sticker-summary");
  if (sum) {
    let s = (data && data.desc) || "无";
    if (data && data.truncated) s += " · 部分图过大，未显示预览";
    sum.textContent = s;
  }
  box.innerHTML = "";
  if (!groups.length) {
    box.innerHTML =
      '<div class="empty">库里还没有图。把图放进插件数据目录的 <code>stickers/&lt;分类&gt;/</code> 即可。</div>';
    return;
  }
  for (const g of groups) {
    const sec = document.createElement("section");
    sec.className = "gallery-group";
    const head = document.createElement("div");
    head.className = "gallery-head";
    head.textContent = g.label;
    const cnt = document.createElement("span");
    cnt.className = "gallery-count";
    cnt.textContent = g.count + " 张";
    head.appendChild(cnt);
    sec.appendChild(head);
    const grid = document.createElement("div");
    grid.className = "gallery-grid";
    for (const img of g.images || []) {
      grid.appendChild(stickerCard(img));
    }
    sec.appendChild(grid);
    box.appendChild(sec);
  }
}

let stickersLoaded = false;

async function loadStickers(force) {
  if (stickersLoaded && !force) return;
  const box = $("sticker-gallery");
  if (box) box.innerHTML = '<div class="empty">读取中 …</div>';
  try {
    const data = await bridge.apiGet("stickers");
    stickersLoaded = true;
    renderStickers(data);
  } catch (e) {
    if (box) box.innerHTML = `<div class="empty">读取表情包失败：${esc(e.message)}</div>`;
  }
}

// ==================== 设置 ====================

function fieldEl(key, sub, sch, value, options) {
  const wrap = document.createElement("div");
  wrap.className = "set-field";

  const name = document.createElement("div");
  name.className = "set-name";
  name.textContent = sch.description || key;
  wrap.appendChild(name);

  wrap.appendChild(makeControl(key, sub, sch, value, options));

  if (sch.hint) {
    const hint = document.createElement("div");
    hint.className = "set-hint";
    hint.textContent = sch.hint;
    wrap.appendChild(hint);
  }
  return wrap;
}

function makeControl(key, sub, sch, value, options) {
  const typ = sch.type || "string";
  const special = sch._special;
  let ctrl;
  if (special === "select_persona" || special === "select_provider") {
    ctrl = document.createElement("select");
    const isPersona = special === "select_persona";
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = isPersona ? "（跟随 AstrBot 默认人格）" : "（用 AstrBot 默认模型）";
    ctrl.appendChild(blank);
    const list = (options && options[isPersona ? "persona" : "provider"]) || [];
    for (const it of list) {
      const op = document.createElement("option");
      op.value = it.id;
      op.textContent = it.name || it.id;
      ctrl.appendChild(op);
    }
    const want = value === null || value === undefined ? "" : String(value);
    ctrl.value = want;
    if (want && ctrl.value !== want) {
      const op = document.createElement("option");
      op.value = want;
      op.textContent = want + "（当前值，不在列表中）";
      ctrl.appendChild(op);
      ctrl.value = want;
    }
  } else if (typ === "bool") {
    ctrl = document.createElement("input");
    ctrl.type = "checkbox";
    ctrl.checked = !!value;
  } else if (typ === "int" || typ === "float") {
    ctrl = document.createElement("input");
    ctrl.type = "number";
    ctrl.step = typ === "int" ? "1" : "0.01";
    ctrl.value = value === null || value === undefined ? "" : String(value);
  } else if (typ === "text") {
    ctrl = document.createElement("textarea");
    ctrl.rows = 3;
    ctrl.value = value === null || value === undefined ? "" : String(value);
  } else {
    ctrl = document.createElement("input");
    ctrl.type = "text";
    ctrl.value = value === null || value === undefined ? "" : String(value);
  }
  ctrl.classList.add("set-input");
  ctrl.dataset.key = key;
  if (sub) ctrl.dataset.sub = sub;
  return ctrl;
}

function renderSettings(payload) {
  const box = $("settings");
  if (!box) return;
  const schema = (payload && payload.schema) || {};
  const values = (payload && payload.values) || {};
  const options = (payload && payload.options) || {};
  const keys = Object.keys(schema);
  box.innerHTML = "";
  if (!keys.length) {
    box.innerHTML = '<div class="empty">读不到配置结构（_conf_schema.json）。</div>';
    return;
  }
  for (const key of keys) {
    const sch = schema[key] || {};
    if (sch.type === "object") {
      const det = document.createElement("details");
      det.className = "set-group";
      det.open = true;
      const sum = document.createElement("summary");
      sum.textContent = sch.description || key;
      det.appendChild(sum);
      const body = document.createElement("div");
      body.className = "set-group-body";
      if (sch.hint) {
        const gh = document.createElement("div");
        gh.className = "set-hint set-group-hint";
        gh.textContent = sch.hint;
        body.appendChild(gh);
      }
      const cur = values[key] && typeof values[key] === "object" ? values[key] : {};
      for (const [sub, subsch] of Object.entries(sch.items || {})) {
        body.appendChild(fieldEl(key, sub, subsch, cur[sub], options));
      }
      det.appendChild(body);
      box.appendChild(det);
    } else {
      box.appendChild(fieldEl(key, "", sch, values[key], options));
    }
  }
}

function collectValues() {
  const payload = {};
  for (const ctrl of document.querySelectorAll(".set-input")) {
    const key = ctrl.dataset.key;
    if (!key) continue;
    let v;
    if (ctrl.type === "checkbox") v = ctrl.checked;
    else if (ctrl.type === "number") v = ctrl.value === "" ? 0 : Number(ctrl.value);
    else v = ctrl.value;
    const sub = ctrl.dataset.sub;
    if (sub) {
      if (!payload[key] || typeof payload[key] !== "object") payload[key] = {};
      payload[key][sub] = v;
    } else {
      payload[key] = v;
    }
  }
  return payload;
}

function setSettingsResult(message, isError) {
  const node = $("settings-result");
  if (!node) return;
  if (!message) {
    node.hidden = true;
    node.textContent = "";
    return;
  }
  node.hidden = false;
  node.classList.toggle("err", !!isError);
  node.textContent = message;
}

async function loadSettings() {
  const box = $("settings");
  if (box) box.innerHTML = '<div class="empty">读取中 …</div>';
  try {
    const data = await bridge.apiGet("settings");
    renderSettings(data);
  } catch (e) {
    if (box) box.innerHTML = `<div class="empty">读取设置失败：${esc(e.message)}</div>`;
  }
}

function saveSettings() {
  return withButton("save-settings", "正在保存设置 ……", async () => {
    try {
      const payload = collectValues();
      const data = await bridge.apiPost("settings", payload);
      if (data && data.status) render(data.status);
      setSettingsResult("已保存。", false);
      showNotice("");
      await loadSettings();
    } catch (e) {
      setSettingsResult(`保存失败：${e.message}`, true);
      showNotice(`保存失败：${e.message}`, true);
    }
  });
}

// ==================== 操作按钮 ====================

const CONFIRM_LABEL = "再点一次确认发送";
const TEST_LABEL = "测试发一条";
let testArmed = false;
let testArmTimer = null;

function disarmTest() {
  testArmed = false;
  if (testArmTimer) {
    clearTimeout(testArmTimer);
    testArmTimer = null;
  }
  const btn = $("test-moment");
  if (btn) btn.textContent = TEST_LABEL;
}

function testMoment() {
  if (!testArmed) {
    testArmed = true;
    const btn = $("test-moment");
    if (btn) btn.textContent = CONFIRM_LABEL;
    showNotice("这会真的往 QQ 空间发一条动态。再点一次该按钮确认，8 秒内有效。", true);
    testArmTimer = setTimeout(disarmTest, 8000);
    return;
  }
  disarmTest();
  return withButton("test-moment", "正在生成并发布，稍等……", async () => {
    try {
      const data = await bridge.apiPost("test-moment", {});
      render(data);
      renderTestResult(data.result);
      showNotice(data.result && data.result.ok ? "" : "发布未成功，看下面结果。");
    } catch (e) {
      showNotice(`发布失败：${e.message}`, true);
    }
  });
}

function reschedule() {
  return withButton("reschedule", "正在重算作息（读人设 → 问模型 → 存盘）……", async () => {
    try {
      const data = await bridge.apiPost("reschedule", {});
      render(data);
      showNotice(
        data.persona_set ? "作息已重算。" : "已重算，但人设为空，结果是保守默认。",
        !data.persona_set,
      );
    } catch (e) {
      showNotice(`重算失败：${e.message}`, true);
    }
  });
}

function stickerReload() {
  return withButton("sticker-reload", "正在重扫表情包目录……", async () => {
    try {
      const data = await bridge.apiPost("sticker-reload", {});
      render(data);
      const node = $("sticker-result");
      if (node) {
        node.hidden = false;
        node.classList.remove("err");
        node.textContent = `已重扫：${data.sticker_desc ?? DASH}`;
      }
      stickersLoaded = false;
      showNotice("");
    } catch (e) {
      showNotice(`重扫失败：${e.message}`, true);
    }
  });
}

function bind() {
  $("refresh")?.addEventListener("click", refresh);
  $("reschedule")?.addEventListener("click", reschedule);
  $("test-moment")?.addEventListener("click", testMoment);
  $("sticker-reload")?.addEventListener("click", stickerReload);
  $("sticker-refresh")?.addEventListener("click", () => loadStickers(true));
  $("save-settings")?.addEventListener("click", saveSettings);
  $("reload-settings")?.addEventListener("click", () => {
    setSettingsResult("");
    loadSettings();
  });
  bridge?.onContext?.(() => {
    document.title = bridge.t?.("pages.status.title", "图恒宇 · 运行状态") ?? document.title;
  });
}

bind();
setupTabs();
refresh();
loadSettings();
setInterval(refresh, 30000);
