// Canonical adapter source: adapter/web/app.js
const providerDefaults = {
  openrouter: {
    label: "OpenRouter",
    apiKeyEnv: "OPENROUTER_API_KEY",
    apiKeyRequired: true,
    baseUrl: "https://openrouter.ai/api/v1",
    sampleModel: "openai/gpt-5-mini",
  },
  openai: {
    label: "OpenAI",
    apiKeyEnv: "OPENAI_API_KEY",
    apiKeyRequired: true,
    baseUrl: "https://api.openai.com/v1",
    sampleModel: "gpt-5-mini",
  },
  anthropic: {
    label: "Anthropic",
    apiKeyEnv: "ANTHROPIC_API_KEY",
    apiKeyRequired: true,
    baseUrl: "",
    sampleModel: "claude-sonnet-4-5",
  },
  zai: {
    label: "GLM / Z.ai",
    apiKeyEnv: "GLM_API_KEY",
    apiKeyRequired: true,
    baseUrl: "https://api.z.ai/api/paas/v4",
    sampleModel: "glm-4.6",
  },
  "kimi-coding": {
    label: "Kimi / Moonshot",
    apiKeyEnv: "KIMI_API_KEY",
    apiKeyRequired: true,
    baseUrl: "https://api.moonshot.ai/v1",
    sampleModel: "kimi-k2-0711-preview",
  },
  deepseek: {
    label: "DeepSeek",
    apiKeyEnv: "DEEPSEEK_API_KEY",
    apiKeyRequired: true,
    baseUrl: "https://api.deepseek.com/v1",
    sampleModel: "deepseek-chat",
  },
  ollama: {
    label: "Ollama",
    apiKeyEnv: "OLLAMA_API_KEY",
    apiKeyRequired: false,
    baseUrl: "http://127.0.0.1:11434/v1",
    sampleModel: "qwen3:14b",
  },
  lmstudio: {
    label: "LM Studio",
    apiKeyEnv: "OPENAI_API_KEY",
    apiKeyRequired: false,
    baseUrl: "http://127.0.0.1:1234/v1",
    sampleModel: "local-model",
  },
  custom: {
    label: "Custom OpenAI-Compatible",
    apiKeyEnv: "OPENAI_API_KEY",
    apiKeyRequired: true,
    baseUrl: "",
    sampleModel: "your-model-id",
  },
};

const providerModelPresets = {
  openrouter: [
    { id: "openai/gpt-5-mini", note: "当前默认建议，适合首轮验证。" },
    { id: "anthropic/claude-sonnet-4-5", note: "通用强项，适合长上下文。 " },
    { id: "deepseek/deepseek-chat", note: "成本更低，适合常规对话。" },
    { id: "moonshotai/kimi-k2-0711-preview", note: "代码与中文表现都比较稳。" },
  ],
  openai: [
    { id: "gpt-5", note: "更强的推理与工具使用能力。" },
    { id: "gpt-5-mini", note: "延迟与成本更友好，适合默认模型。" },
    { id: "gpt-4.1", note: "兼容性更高的通用备选。" },
  ],
  anthropic: [
    { id: "claude-sonnet-4-5", note: "均衡型默认选择。" },
    { id: "claude-opus-4", note: "更重推理场景。" },
    { id: "claude-haiku-4", note: "更快、更轻量。" },
  ],
  zai: [
    { id: "glm-4.6", note: "当前推荐的通用模型。" },
    { id: "glm-4.5-air", note: "更轻量的快速版本。" },
  ],
  "kimi-coding": [
    { id: "kimi-k2-0711-preview", note: "当前推荐，偏向代码与复杂任务。" },
    { id: "moonshot-v1-8k", note: "兼容旧链路时可作回退。" },
  ],
  deepseek: [
    { id: "deepseek-chat", note: "通用默认模型。" },
    { id: "deepseek-reasoner", note: "更偏推理。" },
  ],
  ollama: [
    { id: "qwen3:14b", note: "本地部署常见默认值。" },
    { id: "llama3.1:8b", note: "更轻量的本地通用模型。" },
    { id: "deepseek-r1:14b", note: "本地推理型模型。" },
  ],
  lmstudio: [
    { id: "local-model", note: "占位值；按本机实际模型名替换。" },
    { id: "qwen/qwen3-coder", note: "如果 LM Studio 暴露 OpenAI 兼容名称，可直接填。" },
  ],
  custom: [
    { id: "your-model-id", note: "按你的网关或聚合服务实际模型 ID 填写。" },
  ],
};

const WORKSPACE_TAB_STORAGE_KEY = "trimHermesWorkspaceTabV2";

const stageMeta = {
  configure: {
    badge: "Step 1 / 配置模型",
    summary: "先保存供应商、默认模型和 API key，控制层才能持续生成稳定的 config.yaml 与 .env。",
    hero: "当前主要工作是完成模型配置并落盘。",
    next: "保存配置，然后确认控制层能找到 Hermes runtime。",
    action: "save",
    actionLabel: "保存配置",
  },
  "bundle-runtime": {
    badge: "Step 2 / 补齐 Runtime",
    summary: "模型配置已经就绪，但当前包内还没有可执行的 Hermes runtime，或者系统里没有 `hermes` 命令。",
    hero: "这一步不在 Web 页里完成，需要把 Hermes 打进 `app/runtime/python/` 或提供系统命令。",
    next: "补齐 runtime 后刷新状态，直到命令解析成功。",
    action: "refresh",
    actionLabel: "刷新状态",
  },
  "start-runtime": {
    badge: "Step 3 / 启动 Runtime",
    summary: "配置和命令解析都已经就绪，现在可以由控制层拉起 Hermes gateway 和内部 api_server。",
    hero: "首轮引导基本完成，下一步只剩启动 runtime。",
    next: "点击启动 Hermes，观察日志直到 api_server healthy。",
    action: "start",
    actionLabel: "启动 Hermes",
  },
  warming: {
    badge: "Step 4 / 等待 API Server",
    summary: "Hermes 进程已经启动，但 api_server 还在预热或与模型后端建立连接。",
    hero: "保持页面开启；控制台会继续刷新状态和日志。",
    next: "查看 gateway 日志，等待 API Server 切到 healthy。",
    action: "refresh",
    actionLabel: "重新探测",
  },
  ready: {
    badge: "Ready / 可对话",
    summary: "api_server 已经可用，现在可以在同一屏里验证模型、会话、日志和基础聊天链路。",
    hero: "当前这版控制台已经具备首轮交付能力。",
    next: "挑一个示例提示词，确认回复稳定后再进入更完整的工作流。",
    action: "refresh",
    actionLabel: "刷新状态",
  },
};

function generateSessionId() {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }

  if (cryptoApi && typeof cryptoApi.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    cryptoApi.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0"));
    return [
      hex.slice(0, 4).join(""),
      hex.slice(4, 6).join(""),
      hex.slice(6, 8).join(""),
      hex.slice(8, 10).join(""),
      hex.slice(10, 16).join(""),
    ].join("-");
  }

  const timestamp = Date.now().toString(16);
  const randomPart = Math.random().toString(16).slice(2);
  return `session-${timestamp}-${randomPart}`;
}

function allSettledCompat(promises) {
  if (typeof Promise.allSettled === "function") {
    return Promise.allSettled(promises);
  }

  return Promise.all(
    promises.map((promise) =>
      Promise.resolve(promise).then(
        (value) => ({ status: "fulfilled", value }),
        (reason) => ({ status: "rejected", reason })
      )
    )
  );
}

const elements = {
  shell: document.querySelector(".shell"),
  workspaceTabs: Array.from(document.querySelectorAll(".tab-chip")),
  tabPanels: Array.from(document.querySelectorAll("[data-tab-panel]")),
  provider: document.getElementById("provider"),
  model: document.getElementById("model"),
  baseUrl: document.getElementById("base-url"),
  approvalsMode: document.getElementById("approvals-mode"),
  apiKey: document.getElementById("api-key"),
  apiKeyHint: document.getElementById("api-key-hint"),
  providerMeta: document.getElementById("provider-meta"),
  configHealth: document.getElementById("config-health"),
  modelPickerToggle: document.getElementById("model-picker-toggle"),
  modelPickerToggleValue: document.getElementById("model-picker-toggle-value"),
  modelPickerPanel: document.getElementById("model-picker-panel"),
  modelSearch: document.getElementById("model-search"),
  modelPicker: document.getElementById("model-picker"),
  modelPickerHint: document.getElementById("model-picker-hint"),
  customModelNote: document.getElementById("custom-model-note"),
  setupMessage: document.getElementById("setup-message"),
  runtimePill: document.getElementById("runtime-pill"),
  stageBadge: document.getElementById("stage-badge"),
  stageSummary: document.getElementById("stage-summary"),
  heroStageCopy: document.getElementById("hero-stage-copy"),
  heroNextStep: document.getElementById("hero-next-step"),
  heroRuntimeCommand: document.getElementById("hero-runtime-command"),
  heroPrimary: document.getElementById("hero-primary"),
  checklist: document.getElementById("checklist"),
  controlStatus: document.getElementById("control-status"),
  gatewayStatus: document.getElementById("gateway-status"),
  apiStatus: document.getElementById("api-status"),
  modelStatus: document.getElementById("model-status"),
  pathHome: document.getElementById("path-home"),
  pathWorkspace: document.getElementById("path-workspace"),
  pathConfig: document.getElementById("path-config"),
  runtimeCommand: document.getElementById("runtime-command"),
  runtimeCandidates: document.getElementById("runtime-candidates"),
  modelCatalog: document.getElementById("model-catalog"),
  modelConfigTestStatus: document.getElementById("model-config-test-status"),
  testModelConfig: document.getElementById("test-model-config"),
  workspaceSummary: document.getElementById("workspace-summary"),
  logSummary: document.getElementById("log-summary"),
  platformsOverviewHint: document.getElementById("platforms-overview-hint"),
  platformCards: document.getElementById("platform-cards"),
  platformActiveKicker: document.getElementById("platform-active-kicker"),
  platformActiveTitle: document.getElementById("platform-active-title"),
  platformActiveStatus: document.getElementById("platform-active-status"),
  platformActiveHint: document.getElementById("platform-active-hint"),
  platformConfigForm: document.getElementById("platform-config-form"),
  platformConfigState: document.getElementById("platform-config-state"),
  platformTestResult: document.getElementById("platform-test-result"),
  testPlatform: document.getElementById("test-platform"),
  savePlatform: document.getElementById("save-platform"),
  saveRestartPlatform: document.getElementById("save-restart-platform"),
  statusJson: document.getElementById("status-json"),
  controlLog: document.getElementById("control-log"),
  gatewayLog: document.getElementById("gateway-log"),
  sessionPill: document.getElementById("session-pill"),
  messages: document.getElementById("messages"),
  chatInput: document.getElementById("chat-input"),
  saveConfig: document.getElementById("save-config"),
  reloadConfig: document.getElementById("reload-config"),
  startRuntime: document.getElementById("start-runtime"),
  stopRuntime: document.getElementById("stop-runtime"),
  restartRuntime: document.getElementById("restart-runtime"),
  sendChat: document.getElementById("send-chat"),
  clearChat: document.getElementById("clear-chat"),
  resetSession: document.getElementById("reset-session"),
};

const state = {
  sessionId: localStorage.getItem("trimHermesSessionId") || generateSessionId(),
  status: null,
  config: null,
  models: [],
  modelsSource: "",
  modelsMessage: "",
  modelConfigTest: {
    ok: null,
    message: "",
  },
  platformOrder: [],
  platformSchemas: {},
  platforms: {},
  activePlatform: "",
  platformDraft: {},
  platformDirty: false,
  platformTestMessage: "",
  modelSelectionMessage: "",
  formDirty: false,
  modelPickerExpanded: false,
  lastPresetBaseUrl: "",
  autoRefreshTimer: 0,
  activeTab: localStorage.getItem(WORKSPACE_TAB_STORAGE_KEY) || "",
};

localStorage.setItem("trimHermesSessionId", state.sessionId);

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function dedupeModelOptions(options) {
  const seen = new Set();
  const deduped = [];
  for (const option of options) {
    if (!option?.id || seen.has(option.id)) {
      continue;
    }
    seen.add(option.id);
    deduped.push(option);
  }
  return deduped;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.message || payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function setBusy(button, busy) {
  if (!button) {
    return;
  }
  button.disabled = busy;
  if (busy) {
    button.dataset.label = button.textContent;
    button.textContent = "处理中...";
    return;
  }
  if (button.dataset.label) {
    button.textContent = button.dataset.label;
  }
}

function appendMessage(role, text) {
  appendMessageToDom(role, text);
}

function appendMessageToDom(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  elements.messages.appendChild(bubble);
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function renderSessionMessages(messages = []) {
  elements.messages.innerHTML = "";
  if (!messages.length) {
    appendMessageToDom("system", "trim.hermes 工作台已就绪。先保存模型配置，再启动 Hermes runtime。");
    return;
  }
  for (const message of messages) {
    appendMessageToDom(message.role, message.text);
  }
}

function normalizeServerMessages(messages) {
  const normalized = [];
  for (const message of messages || []) {
    const role = String(message?.role || "").trim();
    const content = typeof message?.content === "string" ? message.content.trim() : "";
    if (!content) {
      continue;
    }
    if (role === "user" || role === "assistant" || role === "system") {
      normalized.push({ role, text: content });
    }
  }
  return normalized;
}

async function hydrateSessionTranscriptFromServer() {
  try {
    const payload = await requestJson(`/api/v1/sessions/${encodeURIComponent(state.sessionId)}/messages`);
    const messages = normalizeServerMessages(payload.messages || []);
    if (messages.length) {
      renderSessionMessages(messages);
      return;
    }
  } catch (_error) {
    if (elements.messages.childElementCount > 0) {
      return;
    }
  }
  if (elements.messages.childElementCount === 0) {
    renderSessionMessages([]);
  }
}

function truncateSession(sessionId) {
  if (!sessionId) {
    return "-";
  }
  if (sessionId.length <= 18) {
    return sessionId;
  }
  return `${sessionId.slice(0, 8)}...${sessionId.slice(-6)}`;
}

function formatCommand(command) {
  return Array.isArray(command) && command.length ? command.join(" ") : "";
}

function currentProviderMeta(provider = elements.provider.value) {
  return providerDefaults[provider] || providerDefaults.custom;
}

function providerModelOptions(provider = elements.provider.value) {
  const presets = providerModelPresets[provider] || providerModelPresets.custom;
  const presetOptions = presets.map((item) => ({
    id: item.id,
    note: item.note,
    source: "preset",
  }));
  const runtimeOptions = (state.models || [])
    .map((item) => {
      const id = typeof item === "string" ? item : item?.id || item?.name || "";
      if (!id) {
        return null;
      }
      return {
        id,
        note: "当前运行时在线广播的模型。",
        source: "runtime",
      };
    })
    .filter(Boolean);

  const current = elements.model.value.trim();
  const merged = dedupeModelOptions([...presetOptions, ...runtimeOptions]);
  if (current && !merged.some((item) => item.id === current)) {
    merged.unshift({
      id: current,
      note: "当前输入值不在推荐列表中，按自定义模型处理。",
      source: "custom",
    });
  }
  return merged;
}

function readDraftConfig() {
  return {
    provider: elements.provider.value,
    model: elements.model.value.trim(),
    base_url: elements.baseUrl.value.trim(),
    approvals_mode: elements.approvalsMode.value,
    api_key: elements.apiKey.value.trim(),
  };
}

function modelPickerRequirements() {
  const draft = readDraftConfig();
  const saved = state.config || {};
  const meta = currentProviderMeta(draft.provider);
  const missing = [];

  if (!draft.provider) {
    missing.push("供应商");
  }
  if (!draft.approvals_mode) {
    missing.push("审批选项");
  }

  const hasBaseUrl = Boolean(draft.base_url) || Boolean(meta.baseUrl) || draft.provider === "anthropic";
  if (!hasBaseUrl) {
    missing.push("Base URL");
  }

  const hasSavedKey = saved.provider === draft.provider && Boolean(saved.api_key_configured);
  const hasApiKey = Boolean(draft.api_key) || hasSavedKey || !meta.apiKeyRequired;
  if (!hasApiKey) {
    missing.push("API Key");
  }

  return {
    ready: missing.length === 0,
    missing,
    hasSavedKey,
    meta,
  };
}

function isConfigReady(config) {
  if (!config) {
    return false;
  }
  const provider = String(config.provider || "");
  const model = String(config.model || "");
  const meta = providerDefaults[provider] || providerDefaults.custom;
  const hasKey = Boolean(config.api_key_configured);
  return Boolean(provider && model && (hasKey || !meta.apiKeyRequired));
}

function deriveStage() {
  const setup = state.config || state.status?.setup || {};
  const gateway = state.status?.gateway || {};
  const apiReady = Boolean(gateway.api_server?.ok);
  const runtimeRunning = Boolean(gateway.running);
  const runtimeResolved = Boolean(formatCommand(gateway.hermes_command));

  if (apiReady) {
    return "ready";
  }
  if (runtimeRunning) {
    return "warming";
  }
  if (isConfigReady(setup) && runtimeResolved) {
    return "start-runtime";
  }
  if (isConfigReady(setup) && !runtimeResolved) {
    return "bundle-runtime";
  }
  return "configure";
}

function shouldPreferChatLayout(stage) {
  return ["start-runtime", "warming", "ready"].includes(stage);
}

function preferredTabForStage(stage) {
  return shouldPreferChatLayout(stage) ? "chat" : "setup";
}

function renderPill(running, apiOk) {
  elements.runtimePill.className = "status-pill";
  if (running && apiOk) {
    elements.runtimePill.textContent = "Hermes Ready";
    return;
  }
  if (running) {
    elements.runtimePill.classList.add("neutral");
    elements.runtimePill.textContent = "Hermes Booting";
    return;
  }
  elements.runtimePill.classList.add("warn");
  elements.runtimePill.textContent = "Runtime Stopped";
}

function renderSessionPill() {
  elements.sessionPill.textContent = `session: ${truncateSession(state.sessionId)}`;
}

function renderProviderMeta() {
  const saved = state.config || {};
  const draft = readDraftConfig();
  const meta = currentProviderMeta(draft.provider);
  const baseCopy = meta.baseUrl || "供应商自行决定";
  elements.providerMeta.textContent = `${meta.label} · ${meta.apiKeyEnv}${meta.apiKeyRequired ? " 必填" : " 可留空"} · 默认 ${baseCopy}`;

  if (saved.provider === draft.provider) {
    if (saved.api_key_configured) {
      elements.apiKeyHint.textContent = `当前使用 ${meta.apiKeyEnv}，已配置：${saved.api_key_preview}`;
    } else {
      elements.apiKeyHint.textContent = meta.apiKeyRequired
        ? `当前使用 ${meta.apiKeyEnv}，尚未配置。`
        : `当前使用 ${meta.apiKeyEnv}，可留空。`;
    }
  } else {
    elements.apiKeyHint.textContent = meta.apiKeyRequired
      ? `切换到 ${meta.label} 后，将写入 ${meta.apiKeyEnv}。`
      : `${meta.label} 默认允许不填 ${meta.apiKeyEnv}。`;
  }

  if (state.formDirty) {
    elements.configHealth.textContent = state.modelSelectionMessage
      || "表单有未保存改动；保存后会覆盖当前已落盘的供应商、模型和审批模式。";
    return;
  }

  if (isConfigReady(saved)) {
    const apiServerAuthCopy = saved.api_server_key_configured
      ? `本地 API Server Bearer 已启用：${saved.api_server_key_preview}`
      : "保存配置后将自动生成本地 API Server Bearer key";
    elements.configHealth.textContent = `已保存配置：${saved.provider || "-"} / ${saved.model || meta.sampleModel}；${apiServerAuthCopy}`;
    return;
  }

  elements.configHealth.textContent = `当前配置还不完整。建议先选模型，例如 ${meta.sampleModel}；保存时会自动生成本地 API Server Bearer key。`;
}

function renderConfig(config, options = {}) {
  const force = Boolean(options.force);
  const provider = config.provider || "openrouter";
  const preset = providerDefaults[provider] || providerDefaults.openrouter;

  if (!state.formDirty || force) {
    elements.provider.value = provider;
    elements.model.value = config.model || "";
    elements.baseUrl.value = config.base_url || preset.baseUrl || "";
    elements.approvalsMode.value = config.approvals_mode || "manual";
    elements.apiKey.value = "";
    elements.modelSearch.value = "";
    state.modelSelectionMessage = "";
    state.modelPickerExpanded = false;
    state.lastPresetBaseUrl = preset.baseUrl || "";
    if (force) {
      state.formDirty = false;
    }
  }

  renderProviderMeta();
  renderModelPicker();
}

function renderStage() {
  const stage = deriveStage();
  const meta = stageMeta[stage];
  const command = formatCommand(state.status?.gateway?.hermes_command);

  elements.stageBadge.className = `stage-badge ${stage}`;
  elements.stageBadge.textContent = meta.badge;
  elements.stageSummary.textContent = meta.summary;
  elements.heroStageCopy.textContent = meta.hero;
  elements.heroNextStep.textContent = meta.next;
  elements.heroRuntimeCommand.textContent = command || "尚未找到 Hermes 命令";
  elements.heroPrimary.textContent = meta.actionLabel;
  elements.heroPrimary.dataset.action = meta.action;
}

function renderChecklist() {
  const setup = state.config || {};
  const gateway = state.status?.gateway || {};
  const meta = providerDefaults[setup.provider] || currentProviderMeta(setup.provider || "openrouter");
  const runtimeCommand = formatCommand(gateway.hermes_command);
  const steps = [
    {
      label: "选择供应商",
      done: Boolean(setup.provider),
      detail: setup.provider ? meta.label : "尚未保存供应商。",
    },
    {
      label: "设置默认模型",
      done: Boolean(setup.model),
      detail: setup.model || `建议先填 ${meta.sampleModel}`,
    },
    {
      label: "配置 API 凭据",
      done: Boolean(setup.api_key_configured) || !meta.apiKeyRequired,
      detail: Boolean(setup.api_key_configured)
        ? `${meta.apiKeyEnv} 已配置`
        : meta.apiKeyRequired
          ? `${meta.apiKeyEnv} 尚未配置`
          : `${meta.apiKeyEnv} 可选`,
    },
    {
      label: "锁定 API Server 认证",
      done: Boolean(setup.api_server_key_configured),
      detail: setup.api_server_key_configured
        ? `Bearer 已启用：${setup.api_server_key_preview || "已配置"}`
        : "保存配置或首次启动时将自动生成本地 Bearer key",
    },
    {
      label: "发现 Hermes Runtime",
      done: Boolean(runtimeCommand),
      detail: runtimeCommand || "还没有解析到可执行命令",
    },
    {
      label: "等待 API Server 就绪",
      done: Boolean(gateway.api_server?.ok),
      detail: gateway.api_server?.ok
        ? "api_server healthy"
        : gateway.running
          ? "gateway 已启动，api_server 预热中"
          : "runtime 尚未启动",
    },
  ];

  elements.checklist.innerHTML = steps
    .map(
      (step, index) => `
        <div class="check-item ${step.done ? "done" : "pending"}">
          <div class="check-mark">${step.done ? "OK" : index + 1}</div>
          <div class="check-copy">
            <strong>${escapeHtml(step.label)}</strong>
            <span>${escapeHtml(step.detail)}</span>
          </div>
        </div>
      `
    )
    .join("");
}

function renderModelCatalog() {
  const tags = [];
  for (const item of state.models) {
    const candidate = typeof item === "string" ? item : item?.id || item?.name || "";
    if (candidate) {
      tags.push(candidate);
    }
    if (tags.length >= 8) {
      break;
    }
  }

  if (!tags.length && state.config?.model && !state.modelsMessage) {
    tags.push(`saved: ${state.config.model}`);
  }

  const fallbackMessage = state.modelsMessage
    ? state.modelsMessage
    : "保存配置后，这里会显示供应商返回的模型目录";

  elements.modelCatalog.innerHTML = tags.length
    ? tags.map((tag) => `<span class="tag mono">${escapeHtml(tag)}</span>`).join("")
    : `<span class="tag">${escapeHtml(fallbackMessage)}</span>`;
}

function renderModelPicker() {
  const provider = elements.provider.value;
  const options = providerModelOptions(provider);
  const current = elements.model.value.trim();
  const requirements = modelPickerRequirements();
  const meta = requirements.meta;
  const query = (elements.modelSearch?.value || "").trim().toLowerCase();
  const filteredOptions = options.filter((option) => {
    if (!query) {
      return true;
    }
    if (option.id === current) {
      return true;
    }
    const haystack = `${option.id} ${option.note || ""} ${option.source || ""}`.toLowerCase();
    return haystack.includes(query);
  });

  if (!requirements.ready) {
    state.modelPickerExpanded = false;
  }

  const panelVisible = requirements.ready && state.modelPickerExpanded;

  elements.modelPickerToggle.disabled = !requirements.ready;
  elements.modelPickerToggle.setAttribute("aria-expanded", String(panelVisible));
  elements.modelPickerPanel.hidden = !panelVisible;
  elements.modelPickerToggleValue.textContent = requirements.ready
    ? (current || "点击展开查看后回填到左侧")
    : `还需完成：${requirements.missing.join("、")}`;

  const sourceCopy = state.modelsSource === "provider"
    ? "当前已接入供应商实时模型目录"
    : "当前仅展示推荐模型";
  if (!requirements.ready) {
    elements.modelPickerHint.textContent = `${meta.label} 的模型列表会在前置配置完成后开放。`;
    elements.customModelNote.textContent = `还缺：${requirements.missing.join("、")}。准备好后点击上方“查看可选模型”再展开下拉与筛选。`;
    elements.modelPicker.innerHTML = '<div class="hint model-picker-empty">前置配置完成后，这里会显示模型列表。</div>';
    return;
  }

  const countCopy = query
    ? `当前显示 ${filteredOptions.length} / ${options.length} 条`
    : `当前共 ${options.length} 条`;
  elements.modelPickerHint.textContent = `${meta.label} 下推荐与在线模型合并展示；${sourceCopy}；${countCopy}。`;

  if (!panelVisible) {
    elements.customModelNote.textContent = current
      ? `当前默认模型：${current}。点击上方“查看可选模型”可重新展开下拉与筛选，并回填左侧输入框。`
      : "点击上方“查看可选模型”后，展开下拉列表与搜索筛选；右侧选中会自动回填到左侧输入框。";
    elements.modelPicker.innerHTML = '<div class="hint model-picker-empty">点击上方“查看可选模型”展开列表。</div>';
    return;
  }

  if (state.modelsMessage) {
    elements.customModelNote.textContent = `模型目录状态：${state.modelsMessage}`;
  } else if (query) {
    elements.customModelNote.textContent = filteredOptions.length
      ? `已按“${elements.modelSearch.value.trim()}”筛选模型；列表区域可滚动浏览。`
      : `没有匹配“${elements.modelSearch.value.trim()}”的模型，请换个关键词或直接手动输入。`;
  } else {
    elements.customModelNote.textContent = current && !options.some((item) => item.id === current && item.source !== "custom")
      ? "当前输入是自定义模型；仍然可以继续手动编辑。"
      : "如果列表里没有你要的模型，仍然可以直接在左侧输入框里手动填写。";
  }

  elements.modelPicker.innerHTML = filteredOptions.length
    ? filteredOptions
        .map((option) => {
          const isActive = option.id === current;
          const sourceLabel = option.source === "runtime"
            ? "在线模型"
            : option.source === "custom"
              ? "自定义"
              : "推荐";
          return `
            <button
              type="button"
              class="model-option ${isActive ? "active" : ""} ${option.source === "custom" ? "custom" : ""}"
              data-model-option="${escapeHtml(option.id)}"
            >
              <strong>${escapeHtml(option.id)}</strong>
              <span>${escapeHtml(sourceLabel)} · ${escapeHtml(option.note || "")}</span>
            </button>
          `;
        })
        .join("")
    : query
      ? '<div class="hint model-picker-empty">没有匹配的模型结果。</div>'
      : '<div class="hint model-picker-empty">当前供应商还没有可展示的模型列表。</div>';
}

function clonePlatformValues(values = {}) {
  return JSON.parse(JSON.stringify(values || {}));
}

function ensureActivePlatform() {
  const order = state.platformOrder.filter((item) => state.platformSchemas[item]);
  if (!order.length) {
    state.activePlatform = "";
    state.platformDraft = {};
    return;
  }
  if (!state.activePlatform || !state.platforms[state.activePlatform]) {
    state.activePlatform = order[0];
    state.platformDraft = clonePlatformValues(state.platforms[state.activePlatform]?.values || {});
    state.platformDirty = false;
    state.platformTestMessage = "";
  }
}

function setActivePlatform(platformId) {
  if (!state.platforms[platformId]) {
    return;
  }
  state.activePlatform = platformId;
  state.platformDraft = clonePlatformValues(state.platforms[platformId].values || {});
  state.platformDirty = false;
  state.platformTestMessage = "";
  renderPlatformWorkspace();
}

function platformFieldMarkup(platformId, field, value, secretState = {}) {
  const fieldId = `platform-${platformId}-${field.id}`;
  const fullWidth = field.type === "textarea" ? " full" : "";
  const configuredCopy = secretState.configured
    ? `已配置：${secretState.preview || "已保存"}`
    : "当前未配置";

  if (field.type === "boolean") {
    return `
      <label class="field${fullWidth}">
        <span>${escapeHtml(field.label)}</span>
        <input
          id="${escapeHtml(fieldId)}"
          type="checkbox"
          data-platform-field="${escapeHtml(field.id)}"
          ${value ? "checked" : ""}
        >
      </label>
    `;
  }

  if (field.type === "select") {
    return `
      <label class="field${fullWidth}" for="${escapeHtml(fieldId)}">
        <span>${escapeHtml(field.label)}</span>
        <select id="${escapeHtml(fieldId)}" data-platform-field="${escapeHtml(field.id)}">
          ${(field.options || [])
            .map((option) => `
              <option value="${escapeHtml(option.value)}" ${option.value === value ? "selected" : ""}>${escapeHtml(option.label)}</option>
            `)
            .join("")}
        </select>
      </label>
    `;
  }

  if (field.type === "textarea") {
    return `
      <label class="field full" for="${escapeHtml(fieldId)}">
        <span>${escapeHtml(field.label)}</span>
        <textarea
          id="${escapeHtml(fieldId)}"
          data-platform-field="${escapeHtml(field.id)}"
          placeholder="${escapeHtml(field.placeholder || "")}"
        >${escapeHtml(value || "")}</textarea>
      </label>
    `;
  }

  if (field.type === "secret") {
    return `
      <label class="field${fullWidth}" for="${escapeHtml(fieldId)}">
        <span>${escapeHtml(field.label)}</span>
        <input
          id="${escapeHtml(fieldId)}"
          type="password"
          data-platform-field="${escapeHtml(field.id)}"
          placeholder="${escapeHtml(field.placeholder || "")}"
          value="${escapeHtml(value || "")}"
        >
        <span class="hint">${escapeHtml(configuredCopy)}</span>
      </label>
    `;
  }

  return `
    <label class="field${fullWidth}" for="${escapeHtml(fieldId)}">
      <span>${escapeHtml(field.label)}</span>
      <input
        id="${escapeHtml(fieldId)}"
        type="text"
        data-platform-field="${escapeHtml(field.id)}"
        placeholder="${escapeHtml(field.placeholder || "")}"
        value="${escapeHtml(value || "")}"
      >
    </label>
  `;
}

function renderChatPlatformCards() {
  ensureActivePlatform();

  if (!state.platformOrder.length) {
    elements.platformCards.innerHTML = '<div class="hint model-picker-empty">平台配置 schema 读取中...</div>';
    return;
  }

  elements.platformCards.innerHTML = state.platformOrder
    .filter((platformId) => state.platformSchemas[platformId] && state.platforms[platformId])
    .map((platformId) => {
      const schema = state.platformSchemas[platformId];
      const platform = state.platforms[platformId];
      const isActive = state.activePlatform === platformId;
      const dependencyCopy = platform.dependencies_ok ? "依赖正常" : `依赖异常：${platform.dependencies_message || "未安装"}`;
      return `
        <button
          type="button"
          class="platform-card-button ${isActive ? "active" : ""}"
          data-platform-card="${escapeHtml(platformId)}"
        >
          <strong>${escapeHtml(schema.label)}</strong>
          <span>${escapeHtml(schema.description || "")}</span>
          <span>状态：${escapeHtml(platform.status || "-")} · ${escapeHtml(dependencyCopy)}</span>
        </button>
      `;
    })
    .join("");
}

function renderPlatformEditor() {
  ensureActivePlatform();

  if (!state.activePlatform || !state.platformSchemas[state.activePlatform] || !state.platforms[state.activePlatform]) {
    elements.platformActiveKicker.textContent = "Platform Editor";
    elements.platformActiveTitle.textContent = "选择一个平台";
    elements.platformActiveStatus.textContent = "暂无平台数据";
    elements.platformActiveHint.textContent = "左侧选择平台后，在这里填写参数并测试连接。";
    elements.platformConfigForm.innerHTML = "";
    elements.platformConfigState.textContent = "平台配置状态读取中...";
    elements.platformTestResult.textContent = "尚未执行平台连接测试。";
    elements.testPlatform.disabled = true;
    elements.savePlatform.disabled = true;
    elements.saveRestartPlatform.disabled = true;
    return;
  }

  const platformId = state.activePlatform;
  const schema = state.platformSchemas[platformId];
  const platform = state.platforms[platformId];
  const values = state.platformDraft || {};

  elements.platformActiveKicker.textContent = schema.label;
  elements.platformActiveTitle.textContent = `${schema.label} 接入配置`;
  elements.platformActiveStatus.textContent = platform.status || "未配置";
  elements.platformActiveHint.textContent = schema.description || "填写平台参数后，可测试连接与保存。";

  elements.platformConfigForm.innerHTML = `
    <div class="platform-form-grid">
      ${(schema.fields || [])
        .map((field) => platformFieldMarkup(platformId, field, values[field.id], (platform.secrets || {})[field.id] || {}))
        .join("")}
    </div>
  `;

  elements.platformConfigState.textContent = state.platformDirty
    ? `${schema.label} 表单有未保存改动；保存后需要重启 Hermes gateway 才会生效。`
    : `${schema.label} 当前状态：${platform.status || "未配置"}。保存后可点“保存并重启 Hermes”。`;
  elements.platformTestResult.textContent = state.platformTestMessage || "尚未执行平台连接测试。";
  elements.platformTestResult.classList.toggle("platform-test-result", true);
  elements.testPlatform.disabled = false;
  elements.savePlatform.disabled = false;
  elements.saveRestartPlatform.disabled = false;
}

function renderPlatformWorkspace() {
  const configuredCount = Object.values(state.platforms || {}).filter((item) => item?.configured).length;
  elements.platformsOverviewHint.textContent = `当前已识别 ${state.platformOrder.length || 0} 个平台，其中 ${configuredCount} 个已具备接入凭据。`;
  renderChatPlatformCards();
  renderPlatformEditor();
}

function renderPlatformCards() {
  const status = state.status || {};
  const setup = state.config || {};
  const gateway = status.gateway || {};
  const runtimeCommand = formatCommand(gateway.hermes_command);
  const candidates = gateway.hermes_command_candidates || [];
  const approvalsMode = setup.approvals_mode || "manual";

  elements.runtimeCommand.textContent = runtimeCommand || "尚未找到 Hermes 可执行命令";
  elements.runtimeCandidates.innerHTML = candidates.length
    ? candidates.map((item) => `<span class="tag mono">${escapeHtml(item)}</span>`).join("")
    : '<span class="tag">暂无候选路径</span>';

  renderModelCatalog();
  if (state.modelConfigTest.ok === true) {
    elements.modelConfigTestStatus.textContent = `最近测试通过：${state.modelConfigTest.message}`;
  } else if (state.modelConfigTest.ok === false) {
    elements.modelConfigTestStatus.textContent = `最近测试失败：${state.modelConfigTest.message}`;
  } else {
    elements.modelConfigTestStatus.textContent = "尚未测试模型配置。";
  }

  elements.workspaceSummary.textContent =
    `审批模式 ${approvalsMode}；API auth ${setup.api_server_key_configured ? "Bearer 已启用" : "未启用"}；工作目录 ${status.paths?.workspace_root || "-"}；Hermes Home ${status.paths?.hermes_home || "-"}`;
  elements.logSummary.textContent =
    `${gateway.control_log || "-"}\n${gateway.gateway_log || "-"}`;
}

function renderStatus(status) {
  const gateway = status.gateway || {};
  const setup = status.setup || {};
  const apiServer = gateway.api_server || {};

  renderPill(Boolean(gateway.running), Boolean(apiServer.ok));
  elements.controlStatus.textContent = status.ok ? "online" : "degraded";
  elements.gatewayStatus.textContent = gateway.running ? `pid ${gateway.pid}` : "stopped";
  elements.apiStatus.textContent = apiServer.ok ? "healthy" : "unavailable";
  elements.modelStatus.textContent = setup.model || "-";
  elements.pathHome.textContent = status.paths?.hermes_home || "-";
  elements.pathWorkspace.textContent = status.paths?.workspace_root || "-";
  elements.pathConfig.textContent = status.paths?.config_file || "-";
  elements.statusJson.textContent = JSON.stringify(status, null, 2);

  const stage = deriveStage();
  if (stage === "bundle-runtime") {
    elements.setupMessage.textContent =
      "配置已经就绪，且本地 API Server Bearer 会由控制层托管；当前剩下的阻塞点是包内还没有找到 Hermes runtime。";
  } else if (stage === "start-runtime") {
    elements.setupMessage.textContent =
      "控制层已经解析到 Hermes 命令，并已准备好本地 API Server Bearer。现在可以直接启动 runtime，验证 gateway 与 api_server。";
  } else if (stage === "warming") {
    elements.setupMessage.textContent =
      "Hermes gateway 已经启动，api_server 会通过本地 Bearer 保护；如果健康检查还没通过，优先查看下方 gateway 日志确认模型握手或端口监听状态。";
  } else if (stage === "ready") {
    elements.setupMessage.textContent =
      "当前控制台已处于可对话状态，基础聊天入口会通过控制层代理并携带本地 Bearer。建议先验证 session、模型响应和日志回流。";
  } else {
    elements.setupMessage.textContent =
      "先完成供应商、默认模型和 API key 配置。保存后控制层会把信息写入 Hermes Home 下的 config.yaml 与 .env，并自动生成本地 API Server Bearer key。";
  }
}

function renderSurface() {
  if (!state.status || !state.config) {
    return;
  }
  const stage = deriveStage();
  elements.shell.classList.toggle("chat-first", shouldPreferChatLayout(stage));
  renderConfig(state.config);
  renderStatus(state.status);
  renderStage();
  renderChecklist();
  renderPlatformCards();
  renderModelPicker();
  renderPlatformWorkspace();
  renderSessionPill();
  if (!localStorage.getItem(WORKSPACE_TAB_STORAGE_KEY)) {
    setActiveTab(preferredTabForStage(stage));
  }
  scheduleAutoRefresh();
}

function setActiveTab(tabName) {
  const nextTab = ["setup", "chat", "ops", "platforms"].includes(tabName) ? tabName : "setup";
  state.activeTab = nextTab;
  localStorage.setItem(WORKSPACE_TAB_STORAGE_KEY, nextTab);

  for (const button of elements.workspaceTabs) {
    const isActive = button.dataset.workspaceTab === nextTab;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  }

  for (const panel of elements.tabPanels) {
    const isActive = panel.dataset.tabPanel === nextTab;
    panel.classList.toggle("active", isActive);
    panel.hidden = !isActive;
  }
}

function clearMessages(message) {
  const systemMessage = message || "消息视图已清空；当前 session_id 会继续沿用，除非你手动切换到新会话。";
  elements.messages.innerHTML = "";
  appendMessageToDom("system", systemMessage);
}

function ensureWelcomeMessage() {
  renderSessionMessages([]);
}

function applyProviderPreset(force = false) {
  const preset = currentProviderMeta();
  const current = elements.baseUrl.value.trim();
  if (force || !current || current === state.lastPresetBaseUrl) {
    elements.baseUrl.value = preset.baseUrl || "";
  }
  state.lastPresetBaseUrl = preset.baseUrl || "";
  renderProviderMeta();
  renderModelPicker();
}

function markFormDirty() {
  state.modelSelectionMessage = "";
  state.formDirty = true;
  renderProviderMeta();
  renderModelPicker();
}

async function loadLogs() {
  const [control, gateway] = await Promise.all([
    requestJson("/api/v1/logs?name=control&lines=120"),
    requestJson("/api/v1/logs?name=gateway&lines=120"),
  ]);
  elements.controlLog.textContent = control.lines?.join("\n") || "暂无控制层日志";
  elements.gatewayLog.textContent = gateway.lines?.join("\n") || "暂无 Hermes gateway 日志";
}

async function loadModels() {
  state.models = [];
  state.modelsSource = "";
  state.modelsMessage = "";
  try {
    const payload = await requestJson("/api/v1/models");
    const response = payload.response || {};
    state.models = Array.isArray(response.data) ? response.data : [];
    state.modelsSource = payload.source || "";
    state.modelsMessage = payload.message || "";
  } catch (_error) {
    state.modelsMessage = _error.message || "无法读取供应商模型目录";
  }
  renderModelCatalog();
  renderModelPicker();
}

async function loadPlatformSchemas() {
  const payload = await requestJson("/api/v1/platforms/schema");
  state.platformOrder = Array.isArray(payload.order) ? payload.order : [];
  state.platformSchemas = payload.platforms || {};
}

async function loadPlatforms() {
  try {
    const payload = await requestJson("/api/v1/platforms");
    state.platformOrder = Array.isArray(payload.order) ? payload.order : state.platformOrder;
    state.platforms = payload.platforms || {};
    ensureActivePlatform();
    if (state.activePlatform && state.platforms[state.activePlatform] && !state.platformDirty) {
      state.platformDraft = clonePlatformValues(state.platforms[state.activePlatform].values || {});
    }
  } catch (_error) {
    state.platforms = {};
  }
  renderPlatformWorkspace();
}

async function refreshAll(options = {}) {
  const forceConfig = Boolean(options.forceConfig);
  if (!state.platformOrder.length || !Object.keys(state.platformSchemas).length) {
    try {
      await loadPlatformSchemas();
    } catch (_error) {
      state.platformOrder = [];
      state.platformSchemas = {};
    }
  }
  const [statusPayload, configPayload] = await Promise.all([
    requestJson("/api/v1/status"),
    requestJson("/api/v1/config"),
  ]);

  state.status = statusPayload;
  state.config = configPayload.config || {};
  if (forceConfig) {
    state.formDirty = false;
  }
  renderSurface();

  await allSettledCompat([loadLogs(), loadModels(), loadPlatforms(), hydrateSessionTranscriptFromServer()]);
  renderPlatformCards();
  renderPlatformWorkspace();
}

async function testModelConfig(options = {}) {
  const payloadOverride = options.payloadOverride || readDraftConfig();
  const showAlertOnFailure = Boolean(options.showAlertOnFailure);
  const button = options.button || elements.testModelConfig;

  if (button) {
    setBusy(button, true);
  }

  try {
    const payload = await requestJson("/api/v1/config/test", {
      method: "POST",
      body: JSON.stringify(payloadOverride),
    });
    state.modelConfigTest = {
      ok: true,
      message: payload.message || "模型配置测试通过。",
    };
    renderPlatformCards();
    return true;
  } catch (error) {
    state.modelConfigTest = {
      ok: false,
      message: error.message || "模型配置测试失败。",
    };
    renderPlatformCards();
    if (showAlertOnFailure) {
      window.alert(`模型配置测试失败\n\n${state.modelConfigTest.message}`);
    }
    return false;
  } finally {
    if (button) {
      setBusy(button, false);
    }
  }
}

async function saveConfig() {
  setBusy(elements.saveConfig, true);
  setBusy(elements.heroPrimary, true);
  try {
    const draft = readDraftConfig();
    const payload = await requestJson("/api/v1/config", {
      method: "POST",
      body: JSON.stringify(draft),
    });
    state.config = payload.config || {};
    state.formDirty = false;
    renderConfig(state.config, { force: true });
    const testPassed = await testModelConfig({
      payloadOverride: draft,
      showAlertOnFailure: true,
    });
    appendMessage(
      "system",
      testPassed
        ? "配置已保存，模型配置测试通过。接下来可以启动 Hermes runtime，验证 api_server 和聊天链路。"
        : `配置已保存，但模型配置测试失败：${state.modelConfigTest.message}`
    );
    await refreshAll();
  } catch (error) {
    appendMessage("system", `保存配置失败：${error.message}`);
  } finally {
    setBusy(elements.saveConfig, false);
    setBusy(elements.heroPrimary, false);
  }
}

function readPlatformDraftPayload() {
  return clonePlatformValues(state.platformDraft || {});
}

async function testPlatformConfig() {
  if (!state.activePlatform) {
    return;
  }
  setBusy(elements.testPlatform, true);
  try {
    const payload = await requestJson(`/api/v1/platforms/${encodeURIComponent(state.activePlatform)}/test`, {
      method: "POST",
      body: JSON.stringify(readPlatformDraftPayload()),
    });
    state.platformTestMessage = payload.message || "平台连接测试完成。";
  } catch (error) {
    state.platformTestMessage = `测试失败：${error.message}`;
  } finally {
    setBusy(elements.testPlatform, false);
    renderPlatformWorkspace();
  }
}

async function savePlatformConfig(options = {}) {
  if (!state.activePlatform) {
    return;
  }
  const restartAfter = Boolean(options.restartAfter);
  setBusy(elements.savePlatform, true);
  setBusy(elements.saveRestartPlatform, true);
  try {
    const payload = await requestJson(`/api/v1/platforms/${encodeURIComponent(state.activePlatform)}`, {
      method: "POST",
      body: JSON.stringify(readPlatformDraftPayload()),
    });
    state.platformDirty = false;
    state.platformTestMessage = payload.message || "平台配置已保存。";
    await loadPlatforms();
    if (restartAfter) {
      const restartPayload = await requestJson("/api/v1/runtime/restart", { method: "POST" });
      appendMessage("system", `重启 Hermes：${restartPayload.message || "完成"}`);
      await refreshAll();
    } else {
      renderPlatformWorkspace();
    }
  } catch (error) {
    state.platformTestMessage = `保存失败：${error.message}`;
    renderPlatformWorkspace();
  } finally {
    setBusy(elements.savePlatform, false);
    setBusy(elements.saveRestartPlatform, false);
  }
}

async function runtimeAction(path, button, actionLabel) {
  setBusy(button, true);
  try {
    const payload = await requestJson(path, { method: "POST" });
    appendMessage("system", `${actionLabel}：${payload.message || "完成"}`);
    await refreshAll();
  } catch (error) {
    appendMessage("system", `${actionLabel}失败：${error.message}`);
  } finally {
    setBusy(button, false);
  }
}

async function sendChat() {
  const message = elements.chatInput.value.trim();
  if (!message) {
    return;
  }
  if (!state.status?.gateway?.api_server?.ok) {
    appendMessage("system", "api_server 还没就绪。先启动 Hermes runtime，再尝试发送消息。");
    return;
  }

  setBusy(elements.sendChat, true);
  let sendSucceeded = false;
  appendMessage("user", message);
  elements.chatInput.value = "";
  try {
    const payload = await requestJson("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        session_id: state.sessionId,
        model: elements.model.value.trim(),
      }),
    });
    if (payload.error_type || payload.message) {
      appendMessage("system", `聊天失败：${payload.message || payload.error_type}`);
    } else {
      sendSucceeded = true;
      appendMessage("assistant", payload.assistant_text || JSON.stringify(payload.response || {}, null, 2));
    }
  } catch (error) {
    appendMessage("system", `聊天失败：${error.message}`);
  } finally {
    setBusy(elements.sendChat, false);
    if (sendSucceeded) {
      await allSettledCompat([loadLogs(), refreshAll()]);
    } else {
      await allSettledCompat([loadLogs()]);
    }
  }
}

function resetSession() {
  state.sessionId = generateSessionId();
  localStorage.setItem("trimHermesSessionId", state.sessionId);
  renderSessionPill();
  clearMessages("已切换到新的 session_id。旧会话不会被删除，但当前页面后续请求会使用新会话。");
  hydrateSessionTranscriptFromServer().catch(() => {});
}

function scheduleAutoRefresh() {
  window.clearTimeout(state.autoRefreshTimer);
  if (deriveStage() !== "warming") {
    return;
  }
  state.autoRefreshTimer = window.setTimeout(() => {
    refreshAll().catch((error) => appendMessage("system", `自动刷新失败：${error.message}`));
  }, 3000);
}

function handlePrimaryAction() {
  const action = elements.heroPrimary.dataset.action;
  if (action === "save") {
    saveConfig();
    return;
  }
  if (action === "start") {
    runtimeAction("/api/v1/runtime/start", elements.startRuntime, "启动 Hermes");
    return;
  }
  refreshAll().catch((error) => appendMessage("system", `刷新失败：${error.message}`));
}

elements.modelPicker.addEventListener("click", (event) => {
  const button = event.target.closest("[data-model-option]");
  if (!button) {
    return;
  }
  elements.model.value = button.dataset.modelOption || "";
  elements.modelSearch.value = "";
  state.modelPickerExpanded = false;
  state.modelSelectionMessage = `已将默认模型“${elements.model.value}”回填到左侧输入框；请点击“保存配置”生效。`;
  state.formDirty = true;
  renderProviderMeta();
  renderModelPicker();
});

elements.modelPickerToggle.addEventListener("click", () => {
  if (elements.modelPickerToggle.disabled) {
    return;
  }
  state.modelPickerExpanded = !state.modelPickerExpanded;
  if (!state.modelPickerExpanded) {
    elements.modelSearch.value = "";
  }
  renderModelPicker();
});

elements.modelSearch.addEventListener("input", () => {
  renderModelPicker();
});

for (const button of elements.workspaceTabs) {
  button.addEventListener("click", () => setActiveTab(button.dataset.workspaceTab || "setup"));
}

elements.platformCards.addEventListener("click", (event) => {
  const button = event.target.closest("[data-platform-card]");
  if (!button) {
    return;
  }
  setActivePlatform(button.dataset.platformCard || "");
});

function handlePlatformFieldMutation(event) {
  const field = event.target.closest("[data-platform-field]");
  if (!field || !state.activePlatform) {
    return;
  }
  const fieldId = field.dataset.platformField || "";
  const nextValue = field.type === "checkbox" ? Boolean(field.checked) : field.value;
  state.platformDraft[fieldId] = nextValue;
  state.platformDirty = true;
  state.platformTestMessage = "";
  const schema = state.platformSchemas[state.activePlatform];
  if (schema) {
    elements.platformConfigState.textContent = `${schema.label} 表单有未保存改动；保存后需要重启 Hermes gateway 才会生效。`;
  }
}

elements.platformConfigForm.addEventListener("input", handlePlatformFieldMutation);
elements.platformConfigForm.addEventListener("change", handlePlatformFieldMutation);

elements.provider.addEventListener("change", () => {
  state.modelPickerExpanded = false;
  elements.modelSearch.value = "";
  markFormDirty();
  applyProviderPreset();
});

elements.model.addEventListener("input", markFormDirty);

for (const field of [elements.baseUrl, elements.approvalsMode, elements.apiKey]) {
  field.addEventListener("input", () => {
    state.modelPickerExpanded = false;
    elements.modelSearch.value = "";
    markFormDirty();
  });
}

elements.saveConfig.addEventListener("click", saveConfig);
elements.reloadConfig.addEventListener("click", () => {
  refreshAll({ forceConfig: true }).catch((error) => appendMessage("system", `重新读取失败：${error.message}`));
});
elements.testModelConfig.addEventListener("click", () => {
  testModelConfig({ showAlertOnFailure: true });
});
elements.testPlatform.addEventListener("click", (event) => {
  event.preventDefault();
  testPlatformConfig();
});
elements.savePlatform.addEventListener("click", (event) => {
  event.preventDefault();
  savePlatformConfig();
});
elements.saveRestartPlatform.addEventListener("click", (event) => {
  event.preventDefault();
  savePlatformConfig({ restartAfter: true });
});
elements.startRuntime.addEventListener("click", () => runtimeAction("/api/v1/runtime/start", elements.startRuntime, "启动 Hermes"));
elements.stopRuntime.addEventListener("click", () => runtimeAction("/api/v1/runtime/stop", elements.stopRuntime, "停止 Hermes"));
elements.restartRuntime.addEventListener("click", () => runtimeAction("/api/v1/runtime/restart", elements.restartRuntime, "重启 Hermes"));
elements.sendChat.addEventListener("click", sendChat);
elements.heroPrimary.addEventListener("click", handlePrimaryAction);
elements.clearChat.addEventListener("click", () => clearMessages());
elements.resetSession.addEventListener("click", resetSession);
elements.chatInput.addEventListener("keydown", (event) => {
  if (event.isComposing || event.keyCode === 229) {
    return;
  }
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendChat();
  }
});

setActiveTab(state.activeTab || "setup");
renderSessionPill();
ensureWelcomeMessage();
refreshAll().catch((error) => appendMessage("system", `初始化失败：${error.message}`));
