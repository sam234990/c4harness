const I18N = {
  zh: {
    overview: "总览", callLogs: "调用日志", asyncTasks: "异步任务", workerConfig: "Worker 配置", localService: "本地服务", all: "全部",
    titleOverview: "分流总览", subOverview: "跨项目、跨会话的 worker 使用统计",
    titleCalls: "调用日志", subCalls: "每一次已执行的分流记录与验证结果",
    totalCalls: "总调用次数", delegatedContext: "委托上下文", savedMain: "预估主模型节省", actualWorker: "实际 Worker Token",
    callsUnit: "次已执行调用", estimate: "估算值", coverage: "Token 覆盖 {known}/{total}",
    routingByBackend: "Backend 分流", routingByBackendSub: "调用次数与委托上下文", routedContext: "委托 Token",
    routingTrend: "分流趋势", delegated: "委托", saved: "节省", workerTokens: "Worker", calls: "调用", day: "日", month: "月",
    trendCaption: "按 {bucket}统计 · {metric}", recentCalls: "最近调用", recentCallsSub: "最新完成的 worker 路由", viewAll: "查看全部",
    searchPlaceholder: "搜索任务或 Thread ID", allBackends: "全部 Backend", allModels: "全部模型", allStatuses: "全部状态", allProjects: "全部项目",
    accepted: "已通过", rejected: "未通过", error: "错误", success: "成功", unknown: "未知",
    time: "时间", task: "主任务 / 子任务", model: "模型", status: "状态", actualTokens: "实际 Token", savedTokens: "预估节省",
    noCalls: "没有匹配的调用记录", previous: "上一页", next: "下一页", page: "第 {page} / {pages} 页 · {total} 条",
    callDetail: "调用详情", parentTask: "主任务", workerTask: "Worker 子任务", thread: "Codex Thread", project: "项目", mode: "模式",
    routeReason: "路由原因", tokenDetails: "Token 明细", input: "输入", output: "输出", returned: "返回摘要", summary: "结果摘要",
    risks: "风险", nextSteps: "下一步", verification: "验证", artifacts: "产物", outputPath: "原始输出", patchPath: "Patch 提案",
    notReported: "未报告", never: "暂无调用", updated: "最近调用 {time}", noData: "暂无数据", readOnly: "只读", patch: "Patch",
    titleAsyncTasks: "异步任务", subAsyncTasks: "按 Codex 对话组织的运行状态与未读结果", asyncInbox: "C4 Inbox", asyncAttention: "异步任务需要处理", asyncAttentionSub: "Codex 当前不能被外部 Worker 自动唤醒；结果会可靠保存在这里。", openInbox: "查看异步任务", asyncPageHelp: "按来源 Codex 对话查看正在运行和尚未处理的异步任务。确认表示结果已被用户或 Codex 处理。", refresh: "刷新", noAsyncTasks: "暂无异步任务", unreadTasks: "未读", runningTasks: "运行中", completedTasks: "已结束", acknowledge: "标记已处理", unattached: "未关联对话", pending: "等待中", running: "运行中", completed: "已完成", failed: "失败", cancelled: "已取消", timed_out: "已超时", taskSummary: "任务摘要",
    titleWorkers: "Worker 配置", subWorkers: "全局能力、偏好和执行边界", addWorker: "新增 Worker", resetDefaults: "恢复默认", saveWorkers: "保存配置",
    workerConfigNotice: "Manifest 不保存 API key、Token、Base URL 或其他凭证。Hard 决定能否执行，Soft 决定候选 Worker 的优先级。", enabled: "启用", preference: "整体偏好", remove: "删除", savedConfig: "配置已保存", writeDisabled: "非本机监听时禁止修改配置",
    basicIdentity: "基本信息", hardCapabilities: "Hard Capabilities · 硬约束", softCapabilities: "Soft Capabilities · 能力偏好", hardHelp: "任一必需能力不满足时，该 Worker 会被直接排除。", softHelp: "0 表示不擅长，1 表示强项；后续会由验证历史修正。", harness: "Harness", modelName: "实际模型", modelAlias: "CLI 模型别名", modelAliasHelp: "传给 harness 的选择器，例如 opus；可由 Claude Code 映射到 mimo-v2.5-pro。", adapterDerived: "执行 Adapter（由 Harness 推导）", policyProfile: "策略配置", modalities: "输入模态", tools: "工具", writeIsolation: "写入隔离", network: "联网", structuredOutput: "结构化输出", contextTokens: "上下文 Token", persistentSession: "持续会话", providerProtocol: "Provider 协议", privacyZone: "隐私区域", implementation: "代码实现", debugging: "调试分析", documentation: "文档研究", architecture: "架构设计"
  },
  en: {
    overview: "Overview", callLogs: "Call logs", asyncTasks: "Async tasks", workerConfig: "Worker config", localService: "Local service", all: "All",
    titleOverview: "Routing overview", subOverview: "Worker usage across projects and Codex sessions",
    titleCalls: "Call logs", subCalls: "Executed routes, token usage, and verification results",
    totalCalls: "Total calls", delegatedContext: "Delegated context", savedMain: "Estimated main saved", actualWorker: "Actual worker tokens",
    callsUnit: "executed calls", estimate: "Estimate", coverage: "Token coverage {known}/{total}",
    routingByBackend: "Routing by backend", routingByBackendSub: "Calls and delegated context", routedContext: "delegated tokens",
    routingTrend: "Routing trend", delegated: "Delegated", saved: "Saved", workerTokens: "Worker", calls: "Calls", day: "Day", month: "Month",
    trendCaption: "By {bucket} · {metric}", recentCalls: "Recent calls", recentCallsSub: "Latest completed worker routes", viewAll: "View all",
    searchPlaceholder: "Search task or Thread ID", allBackends: "All backends", allModels: "All models", allStatuses: "All statuses", allProjects: "All projects",
    accepted: "Accepted", rejected: "Rejected", error: "Error", success: "Success", unknown: "Unknown",
    time: "Time", task: "Parent / worker task", model: "Model", status: "Status", actualTokens: "Actual tokens", savedTokens: "Est. saved",
    noCalls: "No matching calls", previous: "Previous", next: "Next", page: "Page {page} / {pages} · {total} records",
    callDetail: "Call detail", parentTask: "Parent task", workerTask: "Worker task", thread: "Codex Thread", project: "Project", mode: "Mode",
    routeReason: "Route reason", tokenDetails: "Token details", input: "Input", output: "Output", returned: "Returned summary", summary: "Result summary",
    risks: "Risks", nextSteps: "Next steps", verification: "Verification", artifacts: "Artifacts", outputPath: "Raw output", patchPath: "Patch proposal",
    notReported: "Not reported", never: "No calls yet", updated: "Latest call {time}", noData: "No data", readOnly: "Read only", patch: "Patch",
    titleAsyncTasks: "Async tasks", subAsyncTasks: "Running state and unread results grouped by Codex conversation", asyncInbox: "C4 Inbox", asyncAttention: "Async tasks need attention", asyncAttentionSub: "Codex cannot currently be awakened by an external worker; results remain safely available here.", openInbox: "Open async tasks", asyncPageHelp: "View running and unread asynchronous tasks by their source Codex conversation. Acknowledge means the result was handled by Codex or the user.", refresh: "Refresh", noAsyncTasks: "No async tasks", unreadTasks: "Unread", runningTasks: "Running", completedTasks: "Finished", acknowledge: "Mark handled", unattached: "Unattached conversation", pending: "Pending", running: "Running", completed: "Completed", failed: "Failed", cancelled: "Cancelled", timed_out: "Timed out", taskSummary: "Task summary",
    titleWorkers: "Worker configuration", subWorkers: "Global capabilities, preferences, and execution boundaries", addWorker: "Add worker", resetDefaults: "Reset defaults", saveWorkers: "Save configuration",
    workerConfigNotice: "The manifest never stores API keys, tokens, base URLs, or credentials. Hard capabilities determine eligibility; soft capabilities rank eligible workers.", enabled: "Enabled", preference: "Overall preference", remove: "Remove", savedConfig: "Configuration saved", writeDisabled: "Configuration writes are disabled when not bound to loopback",
    basicIdentity: "Basic identity", hardCapabilities: "Hard capabilities", softCapabilities: "Soft capabilities", hardHelp: "A worker is excluded when any required hard capability is missing.", softHelp: "0 means weak and 1 means strong; verified history can refine these priors.", harness: "Harness", modelName: "Actual model", modelAlias: "CLI model alias", modelAliasHelp: "Selector passed to the harness, for example opus; Claude Code may map it to mimo-v2.5-pro.", adapterDerived: "Execution adapter (derived from Harness)", policyProfile: "Policy profile", modalities: "Modalities", tools: "Tools", writeIsolation: "Write isolation", network: "Network", structuredOutput: "Structured output", contextTokens: "Context tokens", persistentSession: "Persistent session", providerProtocol: "Provider protocol", privacyZone: "Privacy zone", implementation: "Implementation", debugging: "Debugging", documentation: "Documentation", architecture: "Architecture"
  }
};

const state = {
  lang: localStorage.getItem("cost-router-lang") || (navigator.language.startsWith("zh") ? "zh" : "en"),
  range: "30d", metric: "delegated_tokens", bucket: "day", page: 1, pages: 1,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC", metadata: null,
  workers: null, asyncTasks: null
};
const colors = { claude_cli: "#e56d3f", codex_subagent: "#15966b", opencode: "#3978cf" };
const fallbackColors = ["#8b65c2", "#d09b32", "#2e99a4", "#c95073", "#68747e"];
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const t = (key, vars = {}) => Object.entries(vars).reduce((value, [name, replacement]) => value.replace(`{${name}}`, replacement), I18N[state.lang][key] || key);
const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const backendName = (value) => ({claude_cli:"Claude CLI", codex_subagent:"Codex Subagent", opencode:"OpenCode"}[value] || value.replaceAll("_", " "));
const backendColor = (value) => colors[value] || fallbackColors[Math.abs([...value].reduce((n, char) => n + char.charCodeAt(0), 0)) % fallbackColors.length];
const formatNumber = (value) => new Intl.NumberFormat(state.lang === "zh" ? "zh-CN" : "en-US", {notation: Number(value) >= 100000 ? "compact" : "standard", maximumFractionDigits: 1}).format(Number(value || 0));
const formatFull = (value) => new Intl.NumberFormat(state.lang === "zh" ? "zh-CN" : "en-US").format(Number(value || 0));
const formatDate = (value) => value ? new Intl.DateTimeFormat(state.lang === "zh" ? "zh-CN" : "en-US", {month:"short", day:"numeric", hour:"2-digit", minute:"2-digit"}).format(new Date(value)) : "-";
const BACKEND_BY_HARNESS = {claude_code:"claude_cli", codex:"codex_subagent", opencode:"external_cli", aider:"external_cli"};
const MODALITIES = ["text", "image", "audio", "video"];
const TOOLS = ["read", "grep", "glob", "patch", "execute", "web"];
const SOFT_DIMENSIONS = ["implementation", "debugging", "documentation", "architecture"];
const option = (value, current, label=value) => `<option value="${esc(value)}" ${value === current ? "selected" : ""}>${esc(label)}</option>`;
const check = value => value ? "checked" : "";

async function api(path, params = {}) {
  const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== "" && value != null));
  const response = await fetch(`${path}${query.size ? `?${query}` : ""}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

async function put(path) {
  const response = await fetch(path, {
    method: "PUT",
    headers: {"X-C4-CSRF": state.metadata?.csrf_token || ""},
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

function applyLanguage() {
  document.documentElement.lang = state.lang === "zh" ? "zh-CN" : "en";
  $$('[data-i18n]').forEach(node => node.textContent = t(node.dataset.i18n));
  $$('[data-i18n-placeholder]').forEach(node => node.placeholder = t(node.dataset.i18nPlaceholder));
  $("#lang-button").textContent = state.lang === "zh" ? "EN" : "中文";
  const page = $(".nav-item.active").dataset.page;
  setPageCopy(page);
}

function setPageCopy(page) {
  const copy = {overview:["titleOverview","subOverview"], calls:["titleCalls","subCalls"], "async-tasks":["titleAsyncTasks","subAsyncTasks"], workers:["titleWorkers","subWorkers"]};
  const [title, subtitle] = copy[page] || copy.overview;
  $("#page-title").textContent = t(title);
  $("#page-subtitle").textContent = t(subtitle);
}

async function loadWorkers() {
  state.workers = await api("/api/workers");
  $("#workers-path").textContent = state.workers.path;
  $("#save-workers").disabled = !state.workers.write_enabled;
  $("#workers-message").textContent = state.workers.write_enabled ? "" : t("writeDisabled");
  renderWorkers();
}

function renderWorkers() {
  $("#workers-list").innerHTML = state.workers.workers.map((worker, index) => `<article class="worker-card" data-index="${index}">
    <div class="worker-card-head"><div><strong>${esc(worker.id)}</strong><span class="model-badge">${esc(worker.model_alias || worker.model)}</span></div><div class="worker-head-actions"><label class="switch-row"><input data-worker-field="enabled" type="checkbox" ${check(worker.enabled)}><span class="switch"></span>${esc(t("enabled"))}</label><button class="danger-button remove-worker" type="button">${esc(t("remove"))}</button></div></div>
    <section class="capability-section identity-section"><div class="capability-title"><div><h3>${esc(t("basicIdentity"))}</h3></div></div><div class="worker-fields">
      <label>ID<input data-worker-field="id" value="${esc(worker.id)}"></label>
      <label>${esc(t("harness"))}<select data-worker-field="harness">${[...new Set(["claude_code","codex","opencode","aider",worker.harness])].map(value => option(value, worker.harness)).join("")}</select></label>
      <label>${esc(t("modelName"))}<input data-worker-field="model" value="${esc(worker.model)}" placeholder="mimo-v2.5-pro"></label>
      <label>${esc(t("modelAlias"))}<input data-worker-field="model_alias" value="${esc(worker.model_alias || worker.model)}" placeholder="opus"><small>${esc(t("modelAliasHelp"))}</small></label>
      <label>${esc(t("policyProfile"))}<input data-worker-field="policy_profile" value="${esc(worker.policy_profile)}"></label>
      <label class="wide slider-field"><span>${esc(t("preference"))}</span><div class="slider-line"><span>-1</span><input data-worker-field="preference_bias" type="range" min="-1" max="1" step="0.05" value="${esc(worker.preference_bias)}"><output>${Number(worker.preference_bias).toFixed(2)}</output><span>+1</span></div></label>
    </div></section>
    <section class="capability-section hard-section"><div class="capability-title"><div><h3>${esc(t("hardCapabilities"))}</h3><p>${esc(t("hardHelp"))}</p></div><span class="capability-pill hard-pill">HARD</span></div>
      <div class="choice-group"><span class="field-title">${esc(t("modalities"))}</span><div class="choice-row">${[...new Set([...MODALITIES, ...worker.capabilities.modalities])].map(value => `<label class="choice-chip"><input data-cap-set="modalities" value="${value}" type="checkbox" ${check(worker.capabilities.modalities.includes(value))}><span>${esc(value)}</span></label>`).join("")}</div></div>
      <div class="choice-group"><span class="field-title">${esc(t("tools"))}</span><div class="choice-row">${[...new Set([...TOOLS, ...worker.capabilities.tools])].map(value => `<label class="choice-chip"><input data-cap-set="tools" value="${value}" type="checkbox" ${check(worker.capabilities.tools.includes(value))}><span>${esc(value)}</span></label>`).join("")}</div></div>
      <div class="hard-grid">
        <label>${esc(t("writeIsolation"))}<select data-cap-field="write_isolation">${[...new Set(["none","staged_copy","worktree",worker.capabilities.write_isolation])].map(value => option(value, worker.capabilities.write_isolation)).join("")}</select></label>
        <label>${esc(t("providerProtocol"))}<select data-cap-field="provider_protocol">${[...new Set(["harness_native","responses","chat_completions","mcp",worker.capabilities.provider_protocol])].map(value => option(value, worker.capabilities.provider_protocol)).join("")}</select></label>
        <label>${esc(t("privacyZone"))}<select data-cap-field="privacy_zone">${[...new Set(["local","approved_external","configured_provider",worker.capabilities.privacy_zone])].map(value => option(value, worker.capabilities.privacy_zone)).join("")}</select></label>
        <label>${esc(t("contextTokens"))}<input data-cap-field="context_tokens" type="number" min="0" step="1000" value="${esc(worker.capabilities.context_tokens)}"></label>
      </div>
      <div class="switch-grid"><label class="switch-row"><input data-cap-field="network" type="checkbox" ${check(worker.capabilities.network)}><span class="switch"></span>${esc(t("network"))}</label><label class="switch-row"><input data-cap-field="structured_output" type="checkbox" ${check(worker.capabilities.structured_output)}><span class="switch"></span>${esc(t("structuredOutput"))}</label><label class="switch-row"><input data-cap-field="persistent_session" type="checkbox" ${check(worker.capabilities.persistent_session)}><span class="switch"></span>${esc(t("persistentSession"))}</label></div>
    </section>
    <section class="capability-section soft-section"><div class="capability-title"><div><h3>${esc(t("softCapabilities"))}</h3><p>${esc(t("softHelp"))}</p></div><span class="capability-pill soft-pill">SOFT</span></div><div class="soft-grid">
      ${SOFT_DIMENSIONS.map(dimension => `<label class="slider-field"><span>${esc(t(dimension))}</span><div class="slider-line"><span>0</span><input data-soft-field="${dimension}" type="range" min="0" max="1" step="0.05" value="${esc(worker.capabilities.soft[dimension] ?? 0)}"><output>${Number(worker.capabilities.soft[dimension] ?? 0).toFixed(2)}</output><span>1</span></div></label>`).join("")}
    </div></section>
  </article>`).join("");
  $$(".worker-card").forEach(card => {
    const index = Number(card.dataset.index);
    const worker = state.workers.workers[index];
    card.querySelectorAll("[data-worker-field]").forEach(input => input.addEventListener("input", () => {
      const field = input.dataset.workerField;
      worker[field] = input.type === "checkbox" ? input.checked : input.type === "range" ? Number(input.value) : input.value;
      if (field === "harness") worker.backend = BACKEND_BY_HARNESS[input.value] || worker.backend;
      if (input.type === "range") input.parentElement.querySelector("output").textContent = Number(input.value).toFixed(2);
    }));
    card.querySelectorAll("[data-cap-field]").forEach(input => input.addEventListener("change", () => { worker.capabilities[input.dataset.capField] = input.type === "checkbox" ? input.checked : input.type === "number" ? Number(input.value) : input.value; }));
    card.querySelectorAll("[data-cap-set]").forEach(input => input.addEventListener("change", () => { const field=input.dataset.capSet; worker.capabilities[field] = [...card.querySelectorAll(`[data-cap-set="${field}"]:checked`)].map(item => item.value); }));
    card.querySelectorAll("[data-soft-field]").forEach(input => input.addEventListener("input", () => { worker.capabilities.soft[input.dataset.softField] = Number(input.value); input.parentElement.querySelector("output").textContent = Number(input.value).toFixed(2); }));
    card.querySelector(".remove-worker").addEventListener("click", () => { state.workers.workers.splice(index, 1); renderWorkers(); });
  });
}

async function saveWorkers() {
  const response = await fetch("/api/workers", {method:"PUT", headers:{"Content-Type":"application/json", "X-C4-CSRF":state.workers.csrf_token}, body:JSON.stringify({version:state.workers.version, revision:state.workers.revision, workers:state.workers.workers})});
  const payload = await response.json(); if (!response.ok) throw new Error(payload.error || response.statusText);
  state.workers = {...state.workers, ...payload}; $("#workers-message").textContent = t("savedConfig"); renderWorkers();
}

async function loadMetadata() {
  state.metadata = await api("/api/metadata");
  const path = state.metadata.memory_path;
  $("#ledger-path").textContent = path;
  $("#ledger-path").title = path;
  $("#last-sync").textContent = state.metadata.last_call_at ? t("updated", {time: formatDate(state.metadata.last_call_at)}) : t("never");
  fillSelect("#filter-backend", state.metadata.filters.backends, backendName);
  fillSelect("#filter-model", state.metadata.filters.models, value => value);
  fillSelect("#filter-project", state.metadata.filters.projects, value => value.split("/").filter(Boolean).pop() || value);
}

function fillSelect(selector, values, labeler) {
  const select = $(selector);
  const first = select.options[0];
  select.replaceChildren(first, ...values.map(value => {
    const option = document.createElement("option"); option.value = value; option.textContent = labeler(value); return option;
  }));
}

async function loadOverview() {
  const data = await api("/api/overview", {range: state.range, timezone: state.timezone});
  const total = data.totals;
  const cards = [
    ["totalCalls", total.calls, t("callsUnit")],
    ["delegatedContext", total.delegated_tokens, "Token · " + t("estimate")],
    ["savedMain", total.saved_tokens, "Token · " + t("estimate")],
    ["actualWorker", total.worker_tokens, t("coverage", {known: total.actual_token_calls, total: total.calls})]
  ];
  $("#summary-grid").innerHTML = cards.map(([label, value, foot]) => `<article class="metric-card"><div class="metric-label">${esc(t(label))}</div><div class="metric-value" title="${esc(formatFull(value))}">${esc(formatNumber(value))}</div><div class="metric-foot">${esc(foot)}</div></article>`).join("");
  $("#provider-grid").innerHTML = data.providers.map(item => `<article class="provider-card"><div class="provider-head"><span class="provider-dot" style="background:${backendColor(item.backend)}"></span><span class="provider-name">${esc(backendName(item.backend))}</span><span class="provider-calls">${esc(formatFull(item.calls))} ${esc(t("calls"))}</span></div><div class="provider-number" title="${esc(formatFull(item.delegated_tokens))}">${esc(formatNumber(item.delegated_tokens))}</div><div class="provider-label">${esc(t("routedContext"))}</div></article>`).join("");
}

async function loadChart() {
  const data = await api("/api/timeseries", {range: state.range, bucket: state.bucket, metric: state.metric, timezone: state.timezone});
  $("#chart-caption").textContent = t("trendCaption", {bucket: t(state.bucket), metric: t({delegated_tokens:"delegated",saved_tokens:"saved",worker_tokens:"workerTokens",calls:"calls"}[state.metric])});
  $("#chart-legend").innerHTML = data.backends.map(backend => `<span class="legend-item"><span class="legend-dot" style="background:${backendColor(backend)}"></span>${esc(backendName(backend))}</span>`).join("");
  drawChart(data);
}

function drawChart(data) {
  const svg = $("#usage-chart"), width = 1000, height = 330, left = 58, right = 18, top = 18, bottom = 42;
  const plotW = width - left - right, plotH = height - top - bottom;
  const totals = data.points.map(point => Object.values(point.values).reduce((sum, value) => sum + value, 0));
  const max = Math.max(...totals, 1), roundedMax = niceMax(max);
  const step = plotW / Math.max(data.points.length, 1), barW = Math.max(3, Math.min(34, step * .62));
  const labelEvery = Math.max(1, Math.ceil(data.points.length / 8));
  const labelIndexes = [];
  for (let index = 0; index < data.points.length; index += labelEvery) labelIndexes.push(index);
  const lastIndex = data.points.length - 1;
  if (lastIndex >= 0 && labelIndexes.at(-1) !== lastIndex) {
    if (lastIndex - labelIndexes.at(-1) < Math.max(2, labelEvery / 2)) labelIndexes.pop();
    labelIndexes.push(lastIndex);
  }
  let parts = [`<title>C4Harness usage chart</title>`];
  for (let i = 0; i <= 4; i++) {
    const y = top + plotH * i / 4, value = roundedMax * (4 - i) / 4;
    parts.push(`<line x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" stroke="#e8ebe9" stroke-dasharray="3 4"/><text x="${left-9}" y="${y+4}" text-anchor="end" fill="#8a9297" font-size="10">${esc(formatNumber(value))}</text>`);
  }
  data.points.forEach((point, index) => {
    const x = left + step * index + (step - barW) / 2;
    let yBottom = top + plotH;
    data.backends.forEach(backend => {
      const value = point.values[backend] || 0, barH = value / roundedMax * plotH;
      if (barH > 0) parts.push(`<rect x="${x}" y="${yBottom-barH}" width="${barW}" height="${barH}" rx="2" fill="${backendColor(backend)}"/>`);
      yBottom -= barH;
    });
    parts.push(`<rect class="hover-target" data-index="${index}" x="${left + step*index}" y="${top}" width="${step}" height="${plotH}" fill="transparent"/>`);
    if (labelIndexes.includes(index)) parts.push(`<text x="${x+barW/2}" y="${height-17}" text-anchor="middle" fill="#7c858a" font-size="10">${esc(shortBucket(point.bucket, data.bucket))}</text>`);
  });
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`); svg.innerHTML = parts.join("");
  $$(".hover-target").forEach(rect => rect.addEventListener("mousemove", event => showTooltip(event, data, Number(rect.dataset.index))));
  svg.addEventListener("mouseleave", () => $("#chart-tooltip").style.display = "none");
}

function niceMax(value) { const power = 10 ** Math.floor(Math.log10(value)); return Math.ceil(value / power) * power; }
function shortBucket(value, bucket) { if (bucket === "month") return value; const [, month, day] = value.split("-"); return `${month}/${day}`; }
function showTooltip(event, data, index) {
  const point = data.points[index], tooltip = $("#chart-tooltip"), wrap = $("#chart-wrap"), rect = wrap.getBoundingClientRect();
  tooltip.innerHTML = `<div class="tooltip-title">${esc(point.bucket)}</div>` + data.backends.map(backend => `<div class="tooltip-row"><span>${esc(backendName(backend))}</span><strong>${esc(formatFull(point.values[backend]))}</strong></div>`).join("");
  tooltip.style.display = "block"; tooltip.style.left = `${Math.min(event.clientX - rect.left + 12, rect.width - 175)}px`; tooltip.style.top = `${Math.max(8, event.clientY - rect.top - 30)}px`;
}

async function loadRecent() {
  const data = await api("/api/calls", {range: "all", page: 1, page_size: 6});
  $("#recent-list").innerHTML = data.items.length ? data.items.map(item => `<button class="recent-row" data-id="${item.id}"><div><div class="task-primary">${esc(item.parent_task_label || item.goal)}</div><div class="task-secondary">${esc(item.goal)}</div></div><span class="backend-pill"><span class="provider-dot" style="background:${backendColor(item.backend)}"></span>${esc(backendName(item.backend))}</span><span class="status-pill ${esc(item.display_status)}">${esc(t(item.display_status))}</span><span class="call-number">${item.total_tokens == null ? esc(t("notReported")) : esc(formatFull(item.total_tokens))}</span></button>`).join("") : `<div class="empty-state" style="display:block">${esc(t("noCalls"))}</div>`;
  $$("#recent-list [data-id]").forEach(row => row.addEventListener("click", () => openDetail(row.dataset.id)));
}

function asyncSummaryText(task) {
  return task.latest_notification?.payload?.summary || task.last_worker_summary || "";
}

async function loadAsyncTasks() {
  const data = await api("/api/async-tasks");
  state.asyncTasks = data;
  const {summary, groups} = data;
  const attention = summary.unread_tasks + summary.running;
  const badge = $("#async-nav-badge");
  badge.hidden = attention === 0;
  badge.textContent = formatFull(attention);
  const overview = $("#async-overview");
  overview.hidden = attention === 0;
  $("#async-overview-counts").innerHTML = [
    ["unreadTasks", summary.unread_tasks, "attention"],
    ["runningTasks", summary.running, "running"],
    ["failed", summary.unread_failed, "failed"],
  ].map(([label, value, tone]) => `<div class="async-overview-stat ${tone}"><strong>${esc(formatFull(value))}</strong><span>${esc(t(label))}</span></div>`).join("");

  const list = $("#async-thread-list");
  $("#async-empty").style.display = groups.length ? "none" : "block";
  list.innerHTML = groups.map(group => `<article class="async-thread-group ${group.unread_tasks || group.running_tasks ? "active" : "quiet"}">
    <header class="async-thread-header">
      <div><span class="eyebrow">${esc(t("thread"))}</span><h3>${esc(group.thread_id === "unattached" ? t("unattached") : group.thread_id)}</h3></div>
      <div class="async-thread-counts">${group.unread_tasks ? `<span class="count-pill attention">${esc(t("unreadTasks"))} ${esc(formatFull(group.unread_tasks))}</span>` : ""}${group.running_tasks ? `<span class="count-pill running">${esc(t("runningTasks"))} ${esc(formatFull(group.running_tasks))}</span>` : ""}<span class="completed-count">${esc(t("completedTasks"))} ${esc(formatFull(group.completed_tasks))}</span></div>
    </header>
    <div class="async-task-stack">${group.tasks.map(task => `<div class="async-task-card ${task.unread_count ? "unread" : task.status === "running" || task.status === "pending" ? "running" : "handled"}">
      <div class="async-task-main"><div class="async-task-title"><strong>${esc(task.goal)}</strong><span class="status-pill ${esc(task.status)}">${esc(t(task.status))}</span></div><p>${esc(asyncSummaryText(task) || t("noData"))}</p><div class="async-task-meta"><span>${esc(formatDate(task.updated_at || task.created_at))}</span><span>${esc(task.backend)}</span><span>${esc(task.model || "-")}</span></div></div>
      ${task.unread_count ? `<button class="secondary-button async-ack" data-task-id="${esc(task.id)}">${esc(t("acknowledge"))} · ${esc(formatFull(task.unread_count))}</button>` : ""}
    </div>`).join("")}</div>
  </article>`).join("");
  $$(".async-ack").forEach(button => button.addEventListener("click", async () => {
    button.disabled = true;
    try { await put(`/api/async-tasks/${encodeURIComponent(button.dataset.taskId)}/ack`); await loadAsyncTasks(); }
    catch (error) { button.disabled = false; window.alert(error.message); }
  }));
}

async function loadCalls() {
  const data = await api("/api/calls", {range: "all", backend: $("#filter-backend").value, model: $("#filter-model").value, status: $("#filter-status").value, project: $("#filter-project").value, query: $("#filter-query").value.trim(), page: state.page, page_size: 20});
  state.pages = data.pages;
  $("#calls-body").innerHTML = data.items.map(item => `<tr data-id="${item.id}"><td>${esc(formatDate(item.created_at))}</td><td><div class="task-primary">${esc(item.parent_task_label || item.goal)}</div><div class="task-secondary">${esc(item.goal)}</div></td><td><span class="backend-pill"><span class="provider-dot" style="background:${backendColor(item.backend)}"></span>${esc(backendName(item.backend))}</span></td><td title="${esc(item.model)}">${esc(item.model)}</td><td><span class="status-pill ${esc(item.display_status)}">${esc(t(item.display_status))}</span></td><td>${item.total_tokens == null ? esc(t("notReported")) : esc(formatFull(item.total_tokens))}</td><td>${esc(formatFull(item.estimated_main_tokens_saved))}</td></tr>`).join("");
  $("#calls-empty").style.display = data.items.length ? "none" : "block";
  $("#page-info").textContent = t("page", data); $("#prev-page").disabled = state.page <= 1; $("#next-page").disabled = state.page >= data.pages;
  $$("#calls-body tr").forEach(row => row.addEventListener("click", () => openDetail(row.dataset.id)));
}

async function openDetail(id) {
  const item = await api(`/api/calls/${id}`);
  $("#detail-title").textContent = item.parent_task_label || item.goal;
  const field = (label, value, wide=false, mono=false) => `<div class="detail-field ${wide?"wide":""}"><div class="detail-label">${esc(t(label))}</div><div class="detail-value ${mono?"mono":""}">${esc(value ?? "-")}</div></div>`;
  const list = (title, values) => values?.length ? `<section class="detail-section"><h3>${esc(t(title))}</h3><ul class="detail-list">${values.map(value => `<li>${esc(typeof value === "string" ? value : value.observation || JSON.stringify(value))}</li>`).join("")}</ul></section>` : "";
  $("#drawer-content").innerHTML = `<div class="detail-grid">${field("parentTask", item.parent_task_label || "-")}${field("workerTask", item.goal)}${field("thread", item.source_thread_id || "-", false, true)}${field("project", item.repo, false, true)}${field("mode", t(item.mode === "patch" ? "patch" : "readOnly"))}${field("model", `${backendName(item.backend)} · ${item.model}`)}${field("routeReason", item.route_reason || "-", true)}</div><section class="detail-section"><h3>${esc(t("tokenDetails"))}</h3><div class="detail-grid">${field("input", item.input_tokens == null ? t("notReported") : formatFull(item.input_tokens))}${field("output", item.output_tokens == null ? t("notReported") : formatFull(item.output_tokens))}${field("delegated", formatFull(item.delegated_context_tokens_estimate))}${field("returned", formatFull(item.returned_result_tokens_estimate))}${field("saved", formatFull(item.estimated_main_tokens_saved))}${field("actualTokens", item.total_tokens == null ? t("notReported") : formatFull(item.total_tokens))}</div></section>${item.summary ? `<section class="detail-section"><h3>${esc(t("summary"))}</h3><p>${esc(item.summary)}</p></section>` : ""}${list("risks", item.risks)}${list("nextSteps", item.next_steps)}${item.verification ? `<section class="detail-section"><h3>${esc(t("verification"))}</h3><p>${esc(item.verification.confidence || "-")} · ${esc(t(item.verification.accepted ? "accepted" : "rejected"))}</p></section>` : ""}${item.raw_output_path || item.proposed_patch_path ? `<section class="detail-section"><h3>${esc(t("artifacts"))}</h3><div class="detail-grid">${field("outputPath", item.raw_output_path || "-", true, true)}${field("patchPath", item.proposed_patch_path || "-", true, true)}</div></section>` : ""}`;
  $("#detail-drawer").classList.add("open"); $("#drawer-backdrop").classList.add("open"); $("#detail-drawer").setAttribute("aria-hidden", "false");
}

function closeDetail() { $("#detail-drawer").classList.remove("open"); $("#drawer-backdrop").classList.remove("open"); $("#detail-drawer").setAttribute("aria-hidden", "true"); }
function switchPage(page) {
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.page === page));
  $$(".page").forEach(item => item.classList.toggle("active", item.id === `page-${page}`));
  setPageCopy(page); $("#sidebar").classList.remove("open"); if (page === "calls") loadCalls(); if (page === "async-tasks") loadAsyncTasks(); if (page === "workers") loadWorkers();
}

function bindSegmented(selector, key, callback) {
  $$(selector + " button").forEach(button => button.addEventListener("click", () => {
    $$(selector + " button").forEach(item => item.classList.remove("active")); button.classList.add("active"); state[key] = button.dataset.value; callback();
  }));
}

let searchTimer;
async function init() {
  applyLanguage();
  await loadMetadata();
  await Promise.all([loadOverview(), loadChart(), loadRecent(), loadAsyncTasks()]);
  $$(".nav-item").forEach(item => item.addEventListener("click", () => switchPage(item.dataset.page)));
  $("#view-all").addEventListener("click", () => switchPage("calls"));
  $("#view-async-tasks").addEventListener("click", () => switchPage("async-tasks"));
  $("#refresh-async").addEventListener("click", loadAsyncTasks);
  $("#save-workers").addEventListener("click", () => saveWorkers().catch(error => $("#workers-message").textContent = error.message));
  $("#reset-workers").addEventListener("click", () => { state.workers.workers = structuredClone(state.workers.defaults); renderWorkers(); });
  $("#add-worker").addEventListener("click", () => { const item = structuredClone(state.workers.defaults[0]); item.id = `worker-${state.workers.workers.length + 1}`; state.workers.workers.push(item); renderWorkers(); });
  $("#lang-button").addEventListener("click", async () => { state.lang = state.lang === "zh" ? "en" : "zh"; localStorage.setItem("cost-router-lang", state.lang); applyLanguage(); await Promise.all([loadOverview(), loadChart(), loadRecent(), loadAsyncTasks()]); if ($("#page-calls").classList.contains("active")) loadCalls(); });
  $("#menu-button").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
  bindSegmented("#overview-range", "range", () => Promise.all([loadOverview(), loadChart()]));
  bindSegmented("#chart-metric", "metric", loadChart); bindSegmented("#chart-bucket", "bucket", loadChart);
  ["#filter-backend", "#filter-model", "#filter-status", "#filter-project"].forEach(selector => $(selector).addEventListener("change", () => { state.page = 1; loadCalls(); }));
  $("#filter-query").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.page = 1; loadCalls(); }, 250); });
  $("#prev-page").addEventListener("click", () => { if (state.page > 1) { state.page--; loadCalls(); } });
  $("#next-page").addEventListener("click", () => { if (state.page < state.pages) { state.page++; loadCalls(); } });
  $("#close-drawer").addEventListener("click", closeDetail); $("#drawer-backdrop").addEventListener("click", closeDetail);
  window.addEventListener("keydown", event => { if (event.key === "Escape") closeDetail(); });
  window.setInterval(() => loadAsyncTasks().catch(console.error), 30000);
}

init().catch(error => { console.error(error); $("#page-subtitle").textContent = error.message; });
