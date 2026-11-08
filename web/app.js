/* 电脑管家前端逻辑：导航、实时监控、清理、启动项。 */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const HISTORY = 90;
const cpuHist = [];
const memHist = [];

/* ---------- 工具 ---------- */

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function formatBytes(bytes, digits = 1) {
  bytes = Number(bytes) || 0;
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(i === 0 ? 0 : digits)} ${units[i]}`;
}

function formatSpeed(bytesPerSec) {
  return `${formatBytes(bytesPerSec)}/s`;
}

function setBar(el, percent) {
  if (!el) return;
  el.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  el.classList.toggle("warn", percent >= 70 && percent < 90);
  el.classList.toggle("danger", percent >= 90);
}

async function fetchJSON(url, options) {
  const resp = await fetch(url, options);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

function postJSON(url, body) {
  return fetchJSON(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

function setConn(ok) {
  const dot = $("#conn-dot");
  dot.classList.toggle("ok", ok);
  dot.classList.toggle("err", !ok);
  $("#conn-text").textContent = ok ? "已连接" : "连接断开";
}

/* ---------- 导航与轮询 ---------- */

let activePage = "overview";
let pollTimer = null;

function switchPage(page) {
  activePage = page;
  $$(".nav-item").forEach((btn) => btn.classList.toggle("active", btn.dataset.page === page));
  $$(".page").forEach((sec) => sec.classList.toggle("active", sec.id === `page-${page}`));

  if (page === "overview") {
    startPolling("overview");
    loadOverview();
  } else if (page === "perf") {
    startPolling("perf");
  } else {
    stopPolling();
    if (page === "system") loadSystem();
    if (page === "startup") loadStartup();
  }
}

function startPolling(mode) {
  stopPolling();
  pollOnce(mode);
  pollTimer = setInterval(() => pollOnce(mode), mode === "overview" ? 2000 : 1500);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function pollOnce(mode) {
  try {
    const stats = await fetchJSON("/api/monitor?limit=12");
    setConn(true);
    if (mode === "overview") renderOverview(stats);
    else renderPerf(stats);
  } catch (err) {
    setConn(false);
  }
}

/* ---------- 趋势图 ---------- */

function pushHist(arr, value) {
  arr.push(value);
  if (arr.length > HISTORY) arr.shift();
}

function drawSpark(svg, data, color) {
  if (!svg) return;
  if (data.length < 2) {
    svg.innerHTML = "";
    return;
  }
  const w = 600;
  const h = 120;
  const pad = 6;
  const step = w / (data.length - 1);
  const points = data.map((value, i) => {
    const x = i * step;
    const y = h - pad - (Math.max(0, Math.min(100, value)) / 100) * (h - pad * 2);
    return [x, y];
  });
  const line = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`)
    .join(" ");
  const gradId = `spark-grad-${color.replace("#", "")}`;
  const area = `${line} L${w},${h} L0,${h} Z`;
  svg.innerHTML =
    `<defs><linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">` +
    `<stop offset="0%" stop-color="${color}" stop-opacity="0.3"/>` +
    `<stop offset="100%" stop-color="${color}" stop-opacity="0"/>` +
    `</linearGradient></defs>` +
    `<path d="${area}" fill="url(#${gradId})"/>` +
    `<path d="${line}" fill="none" stroke="${color}" stroke-width="2" ` +
    `stroke-linejoin="round" stroke-linecap="round"/>`;
}

/* ---------- 概览 ---------- */

function renderOverview(stats) {
  $("#ov-cpu").textContent = stats.cpu.total.toFixed(0);
  setBar($("#ov-cpu-bar"), stats.cpu.total);
  $("#ov-cpu-foot").textContent =
    `${stats.cpu.current_mhz} / ${stats.cpu.max_mhz} MHz · ${stats.cpu.per_core.length} 核心`;

  $("#ov-mem").textContent = stats.memory.percent.toFixed(0);
  setBar($("#ov-mem-bar"), stats.memory.percent);
  $("#ov-mem-foot").textContent =
    `${formatBytes(stats.memory.used)} / ${formatBytes(stats.memory.total)}`;

  $("#ov-net").textContent = formatSpeed(stats.network.down_rate);
  $("#ov-net-foot").textContent = `上行 ${formatSpeed(stats.network.up_rate)}`;

  pushHist(cpuHist, stats.cpu.total);
  pushHist(memHist, stats.memory.percent);
  drawSpark($("#spark-cpu"), cpuHist, "#3b82f6");
  drawSpark($("#spark-mem"), memHist, "#06b6d4");
}

async function loadOverview() {
  try {
    const info = await fetchJSON("/api/system");
    $("#ov-uptime").textContent = info.uptime;
    const boot = new Date(info.boot_time * 1000);
    $("#ov-boot").textContent =
      `开机于 ${boot.toLocaleString("zh-CN", { hour12: false })}`;

    const rows = [
      ["操作系统", `${info.os.name} ${info.os.edition} ${info.os.version}`],
      ["主机名", info.hostname],
      ["处理器", info.cpu.name],
      ["核心 / 线程", `${info.cpu.physical} / ${info.cpu.logical}`],
      ["内存容量", formatBytes(info.memory.total)],
      ["显卡", info.gpus.join(" / ") || "未检测到"],
      ["磁盘", info.disks.map((d) => `${d.device} 可用 ${formatBytes(d.free)}`).join("　") || "无"],
      ["网络", info.network.map((n) => `${n.name} ${n.ip}`).join("　") || "未连接"],
    ];
    $("#ov-sysinfo").innerHTML = rows
      .map(([k, v]) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`)
      .join("");
  } catch (err) {
    setConn(false);
  }
}

/* ---------- 性能 ---------- */

function renderPerf(stats) {
  $("#perf-cpu-total").textContent = `${stats.cpu.total.toFixed(1)}%`;

  const cores = $("#perf-cores");
  if (cores.childElementCount !== stats.cpu.per_core.length) {
    cores.innerHTML = stats.cpu.per_core
      .map((_, i) =>
        `<div class="core"><div class="core-label">CPU ${i}</div>` +
        `<div class="core-value" data-core="${i}">0%</div>` +
        `<div class="core-fill" data-fill="${i}"></div></div>`)
      .join("");
  }
  stats.cpu.per_core.forEach((value, i) => {
    const label = cores.querySelector(`[data-core="${i}"]`);
    const fill = cores.querySelector(`[data-fill="${i}"]`);
    if (label) label.textContent = `${value.toFixed(0)}%`;
    if (fill) fill.style.width = `${Math.min(100, value)}%`;
  });
  $("#perf-cpu-freq").textContent =
    `${stats.cpu.current_mhz} MHz / 最大 ${stats.cpu.max_mhz} MHz`;

  $("#perf-mem-total").textContent = `${stats.memory.percent.toFixed(1)}%`;
  setBar($("#perf-mem-bar"), stats.memory.percent);
  $("#perf-mem-used").textContent = formatBytes(stats.memory.used);
  $("#perf-mem-avail").textContent = formatBytes(stats.memory.available);
  $("#perf-swap").textContent = stats.swap.total
    ? `${formatBytes(stats.swap.used)} / ${formatBytes(stats.swap.total)}`
    : "无";

  $("#perf-disk-read").textContent = formatSpeed(stats.disk.read_rate);
  $("#perf-disk-write").textContent = formatSpeed(stats.disk.write_rate);
  $("#perf-net-up").textContent = formatSpeed(stats.network.up_rate);
  $("#perf-net-down").textContent = formatSpeed(stats.network.down_rate);

  $("#perf-procs tbody").innerHTML = stats.processes
    .map((p) =>
      `<tr><td class="name">${esc(p.name)}</td>` +
      `<td class="num">${p.pid}</td>` +
      `<td class="num">${p.cpu.toFixed(1)}%</td>` +
      `<td class="num">${formatBytes(p.rss)}</td></tr>`)
    .join("");
}

/* ---------- 清理 ---------- */

let cleanItems = [];
let cleanSelected = new Set();

function updateCleanButton() {
  const hasSelection = Array.from(cleanSelected).some((key) => {
    const item = cleanItems.find((i) => i.key === key);
    return item && item.size > 0;
  });
  $("#clean-run").disabled = !hasSelection;
}

function renderCleanList() {
  const list = $("#clean-list");
  if (!cleanItems.length) {
    list.innerHTML = '<div class="empty-page">没有可清理的项目</div>';
    return;
  }
  list.innerHTML = cleanItems
    .map((item) => {
      const hasData = item.size > 0;
      const on = hasData && cleanSelected.has(item.key);
      const tag = item.admin ? '<span class="clean-tag">需管理员</span>' : "";
      const files = item.files ? ` · ${item.files} 个文件` : "";
      return (
        `<div class="clean-item ${on ? "on" : ""}">` +
        `<button class="clean-check ${on ? "on" : ""}" data-toggle="${esc(item.key)}"` +
        `${hasData ? "" : " disabled"}></button>` +
        `<div class="clean-info"><div class="clean-name">${esc(item.name)}${tag}</div>` +
        `<div class="clean-desc">${esc(item.desc)}${files}</div></div>` +
        `<div class="clean-size ${hasData ? "" : "muted"}">` +
        `${hasData ? formatBytes(item.size) : "空"}</div></div>`
      );
    })
    .join("");
}

async function scanClean() {
  const btn = $("#clean-scan");
  btn.disabled = true;
  btn.textContent = "扫描中…";
  $("#clean-hint").textContent = "正在扫描，请稍候…";
  $("#clean-result").hidden = true;
  try {
    const res = await postJSON("/api/clean/scan", { keys: null });
    cleanItems = res.items;
    cleanSelected = new Set(res.items.filter((i) => i.size > 0).map((i) => i.key));
    $("#clean-total").textContent = formatBytes(res.total_size);
    $("#clean-hint").textContent = `共 ${res.total_files} 个文件，勾选后点「立即清理」`;
    renderCleanList();
    updateCleanButton();
  } catch (err) {
    $("#clean-hint").textContent = `扫描失败：${err.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "扫描";
  }
}

async function runClean() {
  const keys = Array.from(cleanSelected).filter((key) => {
    const item = cleanItems.find((i) => i.key === key);
    return item && item.size > 0;
  });
  if (!keys.length) return;

  const btn = $("#clean-run");
  btn.disabled = true;
  btn.textContent = "清理中…";
  $("#clean-progress").textContent = "正在清理，请稍候…";

  const notice = $("#clean-result");
  try {
    const res = await postJSON("/api/clean/run", { keys });
    notice.hidden = false;
    notice.className = "notice";
    let msg = `清理完成，释放 ${formatBytes(res.total_freed)}，删除 ${res.total_deleted} 个文件`;
    if (res.total_skipped) msg += `，${res.total_skipped} 个被占用已跳过`;
    notice.textContent = msg;
    $("#clean-progress").textContent = "";
    await scanClean();
  } catch (err) {
    notice.hidden = false;
    notice.className = "notice err";
    notice.textContent = `清理失败：${err.message}`;
    $("#clean-progress").textContent = "";
  } finally {
    btn.textContent = "立即清理";
  }
}

/* ---------- 启动项 ---------- */

let startupNoticeTimer = null;

function showStartupNotice(text, isError) {
  const el = $("#startup-notice");
  el.hidden = false;
  el.className = `notice${isError ? " err" : ""}`;
  el.textContent = text;
  clearTimeout(startupNoticeTimer);
  startupNoticeTimer = setTimeout(() => {
    el.hidden = true;
  }, 4500);
}

function renderStartupTable(selector, items, enabled) {
  const tbody = $(selector);
  if (!items.length) {
    const text = enabled ? "没有启用中的启动项" : "没有已禁用的启动项";
    tbody.innerHTML = `<tr><td colspan="4" class="empty">${text}</td></tr>`;
    return;
  }
  tbody.innerHTML = items
    .map((item) => {
      const attr = enabled ? "disable" : "enable";
      const label = enabled ? "禁用" : "启用";
      const cls = enabled ? "btn small danger" : "btn small";
      return (
        `<tr><td><div class="name">${esc(item.name)}</div>` +
        `<div class="cmd" title="${esc(item.command)}">${esc(item.command)}</div></td>` +
        `<td>${esc(item.location)}</td><td>${esc(item.scope)}</td>` +
        `<td class="act"><button class="${cls}" data-${attr}="${esc(item.id)}">${label}</button></td></tr>`
      );
    })
    .join("");
}

async function loadStartup() {
  try {
    const data = await fetchJSON("/api/startup");
    $("#startup-enabled-count").textContent = data.enabled.length;
    $("#startup-disabled-count").textContent = data.disabled.length;
    renderStartupTable("#startup-enabled tbody", data.enabled, true);
    renderStartupTable("#startup-disabled tbody", data.disabled, false);
  } catch (err) {
    showStartupNotice(`读取失败：${err.message}`, true);
  }
}

async function toggleStartup(btn) {
  const disableId = btn.dataset.disable;
  const enableId = btn.dataset.enable;
  btn.disabled = true;
  try {
    const res = disableId
      ? await postJSON("/api/startup/disable", { id: disableId })
      : await postJSON("/api/startup/enable", { id: enableId });
    if (res.ok) {
      showStartupNotice(disableId ? "已禁用该启动项" : "已恢复该启动项", false);
      await loadStartup();
    } else {
      showStartupNotice(`操作失败：${res.error || "未知错误"}`, true);
      btn.disabled = false;
    }
  } catch (err) {
    showStartupNotice(`操作失败：${err.message}`, true);
    btn.disabled = false;
  }
}

/* ---------- 系统信息 ---------- */

async function loadSystem() {
  try {
    const info = await fetchJSON("/api/system");
    const groups = [
      ["操作系统", [
        ["系统", `${info.os.name} ${info.os.edition}`],
        ["内核版本", info.os.version],
        ["系统架构", info.os.arch],
        ["主机名", info.hostname],
        ["当前用户", info.user],
        ["开机时长", info.uptime],
      ]],
      ["处理器", [
        ["型号", info.cpu.name],
        ["物理核心", info.cpu.physical],
        ["逻辑处理器", info.cpu.logical],
        ["当前频率", `${info.cpu.current_mhz} MHz`],
        ["最大频率", `${info.cpu.max_mhz} MHz`],
      ]],
      ["内存", [
        ["总容量", formatBytes(info.memory.total)],
        ["已使用", formatBytes(info.memory.used)],
        ["可用", formatBytes(info.memory.free)],
        ["交换分区", info.memory.swap_total ? formatBytes(info.memory.swap_total) : "无"],
      ]],
      ["显卡", info.gpus.length
        ? info.gpus.map((g, i) => [`显卡 ${i + 1}`, g])
        : [["显卡", "未检测到"]]],
    ];

    info.disks.forEach((d) => {
      groups.push([`磁盘 ${d.device}`, [
        ["挂载点", d.mount],
        ["文件系统", d.fstype],
        ["总容量", formatBytes(d.total)],
        ["已使用", `${formatBytes(d.used)}（${d.percent}%）`],
        ["可用空间", formatBytes(d.free)],
      ]]);
    });

    if (info.network.length) {
      const netRows = [];
      info.network.forEach((n, i) => {
        netRows.push([`网卡 ${i + 1}`, n.name]);
        netRows.push(["IP 地址", n.ip]);
        netRows.push(["MAC 地址", n.mac]);
      });
      groups.push(["网络", netRows]);
    } else {
      groups.push(["网络", [["状态", "未连接"]]]);
    }

    $("#system-body").innerHTML = groups
      .map(([title, rows]) =>
        `<div class="card sys-group"><div class="sys-group-title">${esc(title)}</div>` +
        `<div class="kv-grid">${rows
          .map(([k, v]) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`)
          .join("")}</div></div>`)
      .join("");
  } catch (err) {
    $("#system-body").innerHTML = `<div class="notice err">读取失败：${esc(err.message)}</div>`;
  }
}

/* ---------- 初始化 ---------- */

function init() {
  $$(".nav-item").forEach((btn) =>
    btn.addEventListener("click", () => switchPage(btn.dataset.page)));

  $("#overview-refresh").addEventListener("click", loadOverview);
  $("#clean-scan").addEventListener("click", scanClean);
  $("#clean-run").addEventListener("click", runClean);
  $("#startup-refresh").addEventListener("click", loadStartup);
  $("#system-refresh").addEventListener("click", loadSystem);

  $("#clean-list").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-toggle]");
    if (!btn || btn.disabled) return;
    const key = btn.dataset.toggle;
    if (cleanSelected.has(key)) cleanSelected.delete(key);
    else cleanSelected.add(key);
    renderCleanList();
    updateCleanButton();
  });

  document.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-disable], button[data-enable]");
    if (btn) toggleStartup(btn);
  });

  switchPage("overview");
}

document.addEventListener("DOMContentLoaded", init);
