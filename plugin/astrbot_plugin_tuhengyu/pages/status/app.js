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
  const mode = data.sticker_separate ? "单独发" : "一起发";
  text(
    "sticker-detail",
    `${data.sticker_desc ?? DASH}（${mode} · 每条 ${Number.isFinite(sp) ? (sp * 100).toFixed(0) : DASH}%）`,
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
  card.dataset.name = img.name || "";
  card.dataset.tag = img.tag || "";
  card.title = "按住拖到别的分类即可归类";
  card.addEventListener("pointerdown", (e) => beginDrag(card, e));
  if (img.b64) {
    const el = document.createElement("img");
    el.loading = "lazy";
    el.alt = img.name;
    el.draggable = false;
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
  fillCategorySelect((data && data.categories) || []);
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
    sec.dataset.drop = g.drop || g.label;
    sec.dataset.label = g.label;
    box.appendChild(sec);
  }
}

// ==================== 表情包：手动拖拽归类（指针实现，触屏 / WebView 通用） ====================
// 不用 HTML5 原生拖放：它在触屏与多数 WebView 里不触发 drop。
// 改为 pointerdown → 移动超过阈值后生成跟随指针的浮层 → 松手时按落点命中分类。

let dragState = null;
let dragGhost = null;

function beginDrag(card, ev) {
  if (ev.button !== undefined && ev.button !== 0) return;
  dragState = {
    name: card.dataset.name || "",
    from: card.dataset.tag || "",
    card,
    startX: ev.clientX,
    startY: ev.clientY,
    active: false,
    target: null,
  };
}

function moveDrag(ev) {
  const st = dragState;
  if (!st) return;
  if (!st.active) {
    if (Math.hypot(ev.clientX - st.startX, ev.clientY - st.startY) < 8) return;
    st.active = true;
    st.card.classList.add("dragging");
    document.body.classList.add("drag-active");
    const src = st.card.querySelector("img");
    dragGhost = document.createElement("img");
    dragGhost.className = "drag-ghost";
    if (src) dragGhost.src = src.src;
    document.body.appendChild(dragGhost);
  }
  if (ev.cancelable) ev.preventDefault();
  if (dragGhost) {
    dragGhost.style.left = ev.clientX + "px";
    dragGhost.style.top = ev.clientY + "px";
  }
  const el = document.elementFromPoint(ev.clientX, ev.clientY);
  const sec = el && el.closest ? el.closest(".gallery-group") : null;
  if (sec !== st.target) {
    if (st.target) st.target.classList.remove("drop-hover");
    st.target = sec;
    if (sec) sec.classList.add("drop-hover");
  }
}

function endDrag() {
  const st = dragState;
  if (!st) return;
  const sec = st.target;
  st.card.classList.remove("dragging");
  if (dragGhost) {
    dragGhost.remove();
    dragGhost = null;
  }
  document.body.classList.remove("drag-active");
  if (sec) sec.classList.remove("drop-hover");
  dragState = null;
  if (!st.active) return; // 只是点击，不是拖动
  if (!sec) {
    setStickerResult("没有落到分类上，已取消。", false);
    return;
  }
  const to = sec.dataset.drop || "";
  const label = sec.dataset.label || to;
  if (!to) return;
  if (st.from === to) {
    setStickerResult("这张图已经在这个分类里了。", false);
    return;
  }
  setStickerResult("正在把 " + st.name + " 移到「" + label + "」…", false);
  bridge
    .apiPost("sticker-move", { name: st.name, from: st.from, to })
    .then((d) => {
      setStickerResult((d && d.message) || "已移动。", false);
      stickersLoaded = false;
      return loadStickers(true);
    })
    .catch((err) => setStickerResult("移动失败：" + err.message, true));
}

window.addEventListener("pointermove", moveDrag, { passive: false });
window.addEventListener("pointerup", endDrag);
window.addEventListener("pointercancel", endDrag);

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

// ==================== 表情包：新建分类 / 上传 ====================

function fillCategorySelect(cats) {
  const sel = $("sticker-category");
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = "";
  if (!cats.length) {
    const o = document.createElement("option");
    o.value = "";
    o.textContent = "（还没有分类）";
    sel.appendChild(o);
    return;
  }
  for (const c of cats) {
    const o = document.createElement("option");
    o.value = c;
    o.textContent = c;
    sel.appendChild(o);
  }
  if (cur && cats.indexOf(cur) >= 0) sel.value = cur;
}

function setStickerResult(message, isError) {
  const node = $("sticker-result");
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

function fileToB64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const s = String(reader.result || "");
      resolve(s.slice(s.indexOf(",") + 1));
    };
    reader.onerror = () => reject(new Error("读取文件失败"));
    reader.readAsDataURL(file);
  });
}

async function autoClassify() {
  const btn = $("sticker-classify");
  if (btn) btn.disabled = true;
  let moved = 0;
  let kept = 0;
  let failed = 0;
  let left = 0;
  let round = 0;
  try {
    // 每批默认 6 张，避免单次请求过久；自动连点直到没有剩余（最多 8 批）
    while (round < 8) {
      round += 1;
      setStickerResult("正在识图归类，逐张判断，稍等 …（第 " + round + " 批）", false);
      const d = await bridge.apiPost("sticker-classify", { limit: 6 });
      const c = (d && d.classify) || {};
      moved += c.moved || 0;
      kept += c.kept || 0;
      failed += c.failed || 0;
      left = c.remaining || 0;
      if (!left || !c.batch || !c.moved) break;
    }
    let msg =
        "归类完成：归入意图 " + moved + "，留在「其他」" + kept + "，失败 " + failed;
      if (failed)
        msg += "（失败通常是识图模型调用失败，检查「设置」里的识图模型是否支持图片）";
      msg += left ? "；还剩 " + left + " 张判不出类目，可再点一次。" : "。";
      setStickerResult(msg, false);
    stickersLoaded = false;
    await loadStickers(true);
  } catch (e) {
    setStickerResult("归类失败：" + e.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function addCategory() {
  const inp = $("sticker-newcat");
  const name = inp && inp.value ? inp.value.trim() : "";
  if (!name) {
    setStickerResult("请先填分类名。", true);
    return;
  }
  const btn = $("sticker-addcat");
  if (btn) btn.disabled = true;
  try {
    const d = await bridge.apiPost("sticker-category", { name: name });
    setStickerResult((d && d.message) || "已新建分类。", false);
    if (inp) inp.value = "";
    stickersLoaded = false;
    await loadStickers(true);
  } catch (e) {
    setStickerResult("新建失败：" + e.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function uploadFiles(files) {
  const list = Array.from(files || []);
  if (!list.length) return;
  const sel = $("sticker-category");
  const cat = sel ? sel.value : "";
  if (!cat) {
    setStickerResult("没有可选的分类，先新建一个。", true);
    return;
  }
  const btn = $("sticker-upload");
  if (btn) btn.disabled = true;
  let ok = 0;
  let fail = 0;
  let lastErr = "";
  for (const f of list) {
    try {
      const b64 = await fileToB64(f);
      await bridge.apiPost("sticker-upload", {
        category: cat,
        filename: f.name,
        data: b64,
      });
      ok += 1;
    } catch (e) {
      fail += 1;
      lastErr = e.message;
    }
  }
  setStickerResult(
    `上传完成：成功 ${ok}，失败 ${fail}${lastErr ? "（" + lastErr + "）" : ""}`,
    fail > 0,
  );
  stickersLoaded = false;
  await loadStickers(true);
  if (btn) btn.disabled = false;
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
    else if (ctrl.type === "number") v = ctrl.value === "" ? "" : Number(ctrl.value);
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
      if (data && data.saved === false) {
        setSettingsResult(
          "已改到内存，但未能落盘：请在 AstrBot 官方插件配置页点一次「保存」，否则重启后会丢。",
          true,
        );
        showNotice("");
      } else {
        setSettingsResult("已保存。", false);
        showNotice("");
      }
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
  $("sticker-addcat")?.addEventListener("click", addCategory);
  $("sticker-upload")?.addEventListener("click", () => $("sticker-file")?.click());
  $("sticker-classify")?.addEventListener("click", autoClassify);
  $("sticker-file")?.addEventListener("change", (e) => {
    const arr = Array.from(e.target.files || []);
    e.target.value = "";
    uploadFiles(arr);
  });
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
