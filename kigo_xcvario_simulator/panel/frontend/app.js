const STORAGE_RUNTIME_URL = "kigo.sim.runtimeUrl";
const STORAGE_BRIDGE_PREFIX = "kigo.sim.bridge.";
const BARO_K1 = 0.190263;
const BARO_K2 = 8.417286e-5;
const BRIDGE_DEFAULTS = {
  primaryPort: 4353,
  flarmPort: 4354,
  readyTimeoutS: 8,
  pollIntervalMs: 1000,
  pollTimeoutMs: 14000,
  vmRuntimeUrl: "http://172.16.119.135:8181",
  vmBridgeTarget: "slawek@172.16.119.135",
  vmIdentity: "/Users/slawekpiela/.ssh/codex_debian_vm",
  vmSimulatorHost: "127.0.0.1",
  vmWorkdir: "/home/slawek/kigo_xcvario_simulator",
};

const runtimeUrlInput = document.getElementById("runtime-url-input");
const connectButton = document.getElementById("connect-button");
const disconnectButton = document.getElementById("disconnect-button");
const refreshButton = document.getElementById("refresh-button");
const deviceSelect = document.getElementById("device-select");
const applyDeviceButton = document.getElementById("apply-device-button");
const connectionStatus = document.getElementById("connection-status");
const statusMessage = document.getElementById("status-message");
const apiErrorNode = document.getElementById("api-error");

const circlingSpeedMinInput = document.getElementById("circling-speed-min-input");
const circlingSpeedMaxInput = document.getElementById("circling-speed-max-input");
const startButton = document.getElementById("start-button");
const pauseButton = document.getElementById("pause-button");
const resetButton = document.getElementById("reset-button");

const manualPhaseSelect = document.getElementById("manual-phase-select");
const manualHeadingInput = document.getElementById("manual-heading-input");
const manualSpeedInput = document.getElementById("manual-speed-input");
const manualBaroAltitudeInput = document.getElementById("manual-baro-altitude-input");
const manualTurnRadiusInput = document.getElementById("manual-turn-radius-input");
const manualClimbMinInput = document.getElementById("manual-climb-min-input");
const manualClimbMaxInput = document.getElementById("manual-climb-max-input");
const manualSinkInput = document.getElementById("manual-sink-input");
const applyManualButton = document.getElementById("apply-manual-button");

const windDirectionInput = document.getElementById("wind-direction-input");
const windSpeedInput = document.getElementById("wind-speed-input");
const applyWindButton = document.getElementById("apply-wind-button");
const oatInput = document.getElementById("oat-input");
const applyOatButton = document.getElementById("apply-oat-button");
const staticPressureInput = document.getElementById("static-pressure-input");
const deviceQnhInput = document.getElementById("device-qnh-input");
const deviceAltitudeInput = document.getElementById("device-altitude-input");
const applyQnhButton = document.getElementById("apply-qnh-button");
const applyDeviceAltitudeButton = document.getElementById("apply-device-altitude-button");

const trafficEnabledInput = document.getElementById("traffic-enabled-input");
const trafficCountInput = document.getElementById("traffic-count-input");
const trafficCollisionInput = document.getElementById("traffic-collision-input");
const applyTrafficButton = document.getElementById("apply-traffic-button");

const ownshipGrid = document.getElementById("ownship-grid");
const trafficTableBody = document.getElementById("traffic-table-body");
const healthGrid = document.getElementById("health-grid");
const vmBridgeTargetInput = document.getElementById("vm-bridge-target-input");
const bridgeStartButton = document.getElementById("bridge-start-button");
const bridgeStopButton = document.getElementById("bridge-stop-button");
const bridgeRestartButton = document.getElementById("bridge-restart-button");
const bridgeStatusButton = document.getElementById("bridge-status-button");
const bridgeErrorNode = document.getElementById("bridge-error");
const bridgeStatusGrid = document.getElementById("bridge-status-grid");
const bridgeDetailsDialog = document.getElementById("bridge-details-dialog");
const bridgeDetailsTitle = document.getElementById("bridge-details-title");
const bridgeDetailsCloseButton = document.getElementById("bridge-details-close-button");
const bridgeDetailsContent = document.getElementById("bridge-details-content");

const state = {
  runtimeUrl: "",
  streamAbortController: null,
  connected: false,
  snapshot: null,
  runtime: null,
};

function loadStoredSettings() {
  const storedRuntimeUrl = localStorage.getItem(STORAGE_RUNTIME_URL);
  runtimeUrlInput.value = isLegacyRuntimeUrl(storedRuntimeUrl)
    ? BRIDGE_DEFAULTS.vmRuntimeUrl
    : storedRuntimeUrl || BRIDGE_DEFAULTS.vmRuntimeUrl;
  localStorage.removeItem("kigo.sim.runtimeToken");
  loadStoredInput(vmBridgeTargetInput, "vmBridgeTarget", BRIDGE_DEFAULTS.vmBridgeTarget);
}

function persistSettings() {
  localStorage.setItem(STORAGE_RUNTIME_URL, runtimeUrlInput.value.trim());
  persistInput(vmBridgeTargetInput, "vmBridgeTarget");
}

function normalizeRuntimeUrl(rawValue) {
  const trimmed = String(rawValue || "").trim();
  return trimmed.replace(/\/+$/, "");
}

function loadStoredInput(node, key, defaultValue) {
  if (!node) {
    return;
  }
  const storedValue = localStorage.getItem(`${STORAGE_BRIDGE_PREFIX}${key}`);
  node.value = isLegacyBridgeTarget(key, storedValue) ? defaultValue : storedValue || defaultValue;
}

function persistInput(node, key) {
  if (!node) {
    return;
  }
  localStorage.setItem(`${STORAGE_BRIDGE_PREFIX}${key}`, node.value.trim());
}

function isLegacyRuntimeUrl(rawValue) {
  const runtimeUrl = normalizeRuntimeUrl(rawValue);
  if (!runtimeUrl) {
    return false;
  }
  try {
    const url = new URL(runtimeUrl);
    return ["127.0.0.1", "localhost", "::1"].includes(url.hostname) && url.port === "8181";
  } catch (_error) {
    return true;
  }
}

function syncRuntimeSettingsFromInputs() {
  state.runtimeUrl = controlApiRuntimeUrl(runtimeUrlInput.value);
  runtimeUrlInput.value = state.runtimeUrl;
  persistSettings();
}

function setStatus(kind, message) {
  connectionStatus.className = `status-pill status-pill--${kind}`;
  connectionStatus.textContent = kind === "ok" ? "Connected" : kind === "error" ? "Error" : "Disconnected";
  statusMessage.textContent = message;
}

function showApiError(message) {
  if (!message) {
    apiErrorNode.hidden = true;
    apiErrorNode.textContent = "";
    return;
  }
  apiErrorNode.hidden = false;
  apiErrorNode.textContent = message;
}

function buildHeaders(includeJson = false) {
  const headers = {};
  if (includeJson) {
    headers["Content-Type"] = "application/json";
  }
  return headers;
}

async function requestJson(path, options = {}) {
  const requestUrl = runtimeUrlForPath(path);
  const response = await fetch(requestUrl, {
    ...options,
    headers: {
      ...buildHeaders(options.body !== undefined),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new Error(message || `${response.status} ${response.statusText}`);
  }
  if (response.status === 204) {
    return null;
  }
  const contentType = response.headers.get("Content-Type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error(
      `Expected simulator JSON from ${response.url}, got ${contentType || "unknown content type"}. Check Runtime URL.`,
    );
  }
  return response.json();
}

function runtimeUrlForPath(path) {
  return new URL(path, `${state.runtimeUrl}/`).toString();
}

async function readErrorMessage(response) {
  const body = await response.text();
  if (!body) {
    return "";
  }
  if (looksLikeHtml(body)) {
    return `${response.status} from ${response.url}. This looks like the panel/static server, not the simulator runtime. Use the control API port, usually http://127.0.0.1:8181.`;
  }
  try {
    const payload = JSON.parse(body);
    return payload.message || payload.error || body;
  } catch (_error) {
    return body;
  }
}

function looksLikeHtml(body) {
  return String(body || "").trimStart().startsWith("<");
}

async function connectPanel() {
  syncRuntimeSettingsFromInputs();
  disconnectPanel();
  const candidates = runtimeUrlCandidates(state.runtimeUrl);
  const errors = [];
  for (const runtimeUrl of candidates) {
    state.runtimeUrl = runtimeUrl;
    runtimeUrlInput.value = runtimeUrl;
    try {
      await fetchState({ syncControls: true });
      await openEventStream();
      state.connected = true;
      persistSettings();
      setStatus("ok", `Panel API connected to ${state.runtimeUrl}. Restarting bridges...`);
      showApiError("");
      await restartBridgesAfterConnect();
      return;
    } catch (error) {
      disconnectPanel();
      errors.push(`${runtimeUrl}: ${String(error.message || error)}`);
    }
  }
  state.connected = false;
  setStatus("error", `Failed to connect to ${candidates[0] || state.runtimeUrl}`);
  showApiError(errors.join("\n"));
}

async function restartBridgesAfterConnect() {
  let bridgePayload = null;
  try {
    bridgePayload = buildBridgePayload();
    setBridgeBusy(true, "restart");
    const payload = await requestJson("/api/v1/bridges/restart", {
      method: "POST",
      body: JSON.stringify(bridgePayload),
    });
    renderBridgeStatus(payload);
    const finalStatus = await pollBridgeStatus(bridgePayload, "restart");
    renderBridgeStatus(finalStatus);
    await fetchState({ syncControls: true }).catch(() => undefined);
    if (bridgesReady(finalStatus)) {
      setStatus("ok", `Panel API connected to ${state.runtimeUrl}. Bridges ready.`);
      showBridgeError("");
    }
  } catch (error) {
    state.connected = true;
    setStatus("error", `Panel API connected to ${state.runtimeUrl}, but bridge restart needs attention.`);
    showBridgeError(String(error.message || error));
  } finally {
    if (bridgePayload) {
      setBridgeBusy(false, "restart");
    }
  }
}

function runtimeUrlCandidates(rawRuntimeUrl) {
  const primary = controlApiRuntimeUrl(rawRuntimeUrl);
  const candidates = [];
  appendUnique(candidates, primary);
  const correctedControlApiUrl = withPort(primary, "8181");
  if (isLikelyPanelUrl(primary)) {
    appendUnique(candidates, correctedControlApiUrl);
  }
  if (!primary) {
    appendUnique(candidates, "http://127.0.0.1:8181");
  }
  return candidates;
}

function controlApiRuntimeUrl(rawRuntimeUrl) {
  const runtimeUrl = normalizeRuntimeUrl(rawRuntimeUrl);
  return isLikelyPanelUrl(runtimeUrl) ? withPort(runtimeUrl, "8181") : runtimeUrl;
}

function isLikelyPanelUrl(runtimeUrl) {
  if (!runtimeUrl) {
    return true;
  }
  try {
    const url = new URL(runtimeUrl);
    return url.port === "8180" || url.host === window.location.host;
  } catch (error) {
    return true;
  }
}

function withPort(runtimeUrl, port) {
  try {
    const url = new URL(runtimeUrl || window.location.origin);
    url.port = port;
    return normalizeRuntimeUrl(url.toString());
  } catch (_error) {
    return `http://127.0.0.1:${port}`;
  }
}

function appendUnique(values, value) {
  if (value && !values.includes(value)) {
    values.push(value);
  }
}

function disconnectPanel() {
  if (state.streamAbortController) {
    state.streamAbortController.abort();
    state.streamAbortController = null;
  }
  if (state.connected) {
    setStatus("idle", "Disconnected from the remote runtime.");
  }
  state.connected = false;
}

async function fetchState({ syncControls = false } = {}) {
  const payload = await requestJson("/api/v1/simulation/state");
  applyStatePayload(payload);
  if (syncControls) {
    syncControlValues();
  }
}

function applyStatePayload(payload) {
  if (!payload) {
    return;
  }
  state.snapshot = payload.snapshot || state.snapshot;
  state.runtime = payload.runtime || state.runtime;
  renderState();
}

async function openEventStream() {
  const controller = new AbortController();
  state.streamAbortController = controller;
  const response = await fetch(`${state.runtimeUrl}/api/v1/events`, {
    headers: buildHeaders(false),
    signal: controller.signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`SSE connect failed: ${response.status} ${response.statusText}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const pump = async () => {
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        buffer = drainSseBuffer(buffer);
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        state.connected = false;
        setStatus("error", "Event stream disconnected. Use Connect to retry.");
        showApiError(String(error.message || error));
      }
    }
  };

  void pump();
}

function drainSseBuffer(buffer) {
  let working = buffer;
  while (working.includes("\n\n")) {
    const boundaryIndex = working.indexOf("\n\n");
    const rawEvent = working.slice(0, boundaryIndex);
    working = working.slice(boundaryIndex + 2);
    handleSseEvent(rawEvent);
  }
  return working;
}

function handleSseEvent(rawEvent) {
  const lines = rawEvent.split("\n");
  let eventName = "message";
  const payloadLines = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      payloadLines.push(line.slice(5).trim());
    }
  }
  if (payloadLines.length === 0) {
    return;
  }
  const payload = JSON.parse(payloadLines.join("\n"));
  if (eventName === "state") {
    applyStatePayload(payload);
    return;
  }
  if (eventName === "ownship" && state.snapshot) {
    state.snapshot.ownship = payload;
  }
  if (eventName === "traffic" && state.snapshot) {
    state.snapshot.traffic = payload;
  }
  if (eventName === "health" && state.snapshot) {
    state.snapshot.health = payload.health;
    state.snapshot.runtime_state = payload.runtime_state;
    state.snapshot.sim_time_s = payload.sim_time_s;
  }
  renderState();
}

async function postCommand(path, payload = null, { syncControls = false } = {}) {
  showApiError("");
  syncRuntimeSettingsFromInputs();
  if (!state.runtimeUrl) {
    showApiError("Runtime URL is required.");
    return;
  }
  try {
    await requestJson(path, {
      method: "POST",
      body: payload ? JSON.stringify(payload) : undefined,
    });
    await fetchState({ syncControls });
  } catch (error) {
    showApiError(formatCommandError(path, error));
  }
}

async function requestBridge(action) {
  showBridgeError("");
  syncRuntimeSettingsFromInputs();
  if (!state.runtimeUrl) {
    showBridgeError("Runtime URL is required.");
    return;
  }
  let isBusy = false;
  try {
    const bridgePayload = buildBridgePayload();
    setBridgeBusy(true, action);
    isBusy = true;
    const payload = await requestJson(`/api/v1/bridges/${action}`, {
      method: "POST",
      body: JSON.stringify(bridgePayload),
    });
    renderBridgeStatus(payload);
    if (action === "status") {
      showBridgeError("");
    }
    if (action !== "status") {
      const finalStatus = await pollBridgeStatus(bridgePayload, action);
      renderBridgeStatus(finalStatus);
      await fetchState().catch(() => undefined);
    }
  } catch (error) {
    showBridgeError(String(error.message || error));
  } finally {
    if (isBusy) {
      setBridgeBusy(false, action);
    }
  }
}

function buildBridgePayload() {
  const payload = {
    primary_port: BRIDGE_DEFAULTS.primaryPort,
    flarm_port: BRIDGE_DEFAULTS.flarmPort,
    ready_timeout_s: BRIDGE_DEFAULTS.readyTimeoutS,
    nodes: [
      bridgeNodeFromTarget(
        "vm",
        vmBridgeTargetInput.value,
        BRIDGE_DEFAULTS.vmIdentity,
        BRIDGE_DEFAULTS.vmSimulatorHost,
        BRIDGE_DEFAULTS.vmWorkdir,
      ),
    ].filter((node) => node.ssh_target && node.simulator_host && node.workdir),
  };
  if (payload.nodes.length === 0) {
    throw new Error("VM bridge target is required.");
  }
  return payload;
}

function bridgeNodeFromTarget(id, sshTarget, identityFile, simulatorHost, workdir) {
  return {
    id,
    ssh_target: String(sshTarget || "").trim(),
    identity_file: identityFile,
    simulator_host: simulatorHost,
    workdir,
  };
}

async function pollBridgeStatus(bridgePayload, action) {
  const waitForReady = action === "start" || action === "restart";
  const waitForStopped = action === "stop";
  const deadline = Date.now() + BRIDGE_DEFAULTS.pollTimeoutMs;
  let latest = null;
  while (Date.now() < deadline) {
    await sleep(BRIDGE_DEFAULTS.pollIntervalMs);
    latest = await requestJson("/api/v1/bridges/status", {
      method: "POST",
      body: JSON.stringify(bridgePayload),
    });
    renderBridgeStatus(latest);
    if (waitForReady && bridgesReady(latest)) {
      showBridgeError("");
      return latest;
    }
    if (waitForStopped && bridgesStopped(latest)) {
      showBridgeError("");
      return latest;
    }
    if (!waitForReady && !waitForStopped) {
      return latest;
    }
  }
  if (latest) {
    showBridgeError(bridgeTimeoutMessage(action, latest));
    return latest;
  }
  throw new Error(`Bridge ${action} did not return status before timeout.`);
}

function bridgesReady(payload) {
  const nodes = payload && Array.isArray(payload.nodes) ? payload.nodes : [];
  return nodes.length > 0 && nodes.every((node) => Boolean(node.ready));
}

function bridgesStopped(payload) {
  const nodes = payload && Array.isArray(payload.nodes) ? payload.nodes : [];
  return nodes.length > 0 && nodes.every((node) => !node.primary_active && !node.flarm_active);
}

function bridgeTimeoutMessage(action, payload) {
  const nodes = payload && Array.isArray(payload.nodes) ? payload.nodes : [];
  const details = nodes
    .map((node) => {
      const id = String(node.id || "bridge").toUpperCase();
      return `${id}: primary=${bridgePartSummary(node, "primary")}, flarm=${bridgePartSummary(node, "flarm")}`;
    })
    .join("; ");
  return `Bridge ${action} timed out. ${details || "No node status returned."}`;
}

function bridgePartSummary(node, prefix) {
  const status = node[`${prefix}_status`] || "unknown";
  const pty = node[`${prefix}_pty_exists`] ? "pty" : "no-pty";
  const tcp = node[`${prefix}_tcp_connected`] ? "tcp" : "no-tcp";
  const error = node[`${prefix}_last_error`];
  return `${status}/${pty}/${tcp}${error ? `/${error}` : ""}`;
}

function setBridgeBusy(isBusy, action) {
  for (const button of [bridgeStartButton, bridgeStopButton, bridgeRestartButton, bridgeStatusButton]) {
    button.disabled = isBusy;
  }
  if (isBusy) {
    showBridgeError(`Bridge ${action} in progress...`);
  }
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isLegacyBridgeTarget(key, storedValue) {
  if (key === "vmBridgeTarget" && storedValue === "codex-vm") {
    return true;
  }
  return key === "piBridgeTarget" && storedValue === "192.168.0.120";
}

function showBridgeError(message) {
  if (!message) {
    bridgeErrorNode.hidden = true;
    bridgeErrorNode.textContent = "";
    return;
  }
  bridgeErrorNode.hidden = false;
  bridgeErrorNode.textContent = message;
}

function formatCommandError(path, error) {
  const message = String(error.message || error);
  if (path === "/api/v1/simulation/oat" && message === "not_found") {
    return "Runtime does not support OAT yet. Pull latest simulator code and restart the remote runtime.";
  }
  return String(error.message || error);
}

function numericValue(node) {
  if (!node.value.trim()) {
    return null;
  }
  return Number(node.value);
}

function syncControlValues() {
  const snapshot = state.snapshot;
  if (!snapshot) {
    return;
  }
  const ownship = snapshot.ownship;
  if (ownship) {
    setSelectValueIfIdle(manualPhaseSelect, ownship.on_ground ? "on_ground" : ownship.phase);
    setNumericValueIfIdle(manualHeadingInput, ownship.track_deg, 1);
    setNumericValueIfIdle(manualSpeedInput, ownship.speed_kmh, 1);
    setNumericValueIfIdle(manualBaroAltitudeInput, ownship.gps_altitude_m, 0);
    setNumericValueIfIdle(staticPressureInput, ownship.static_pressure_hpa, 2);
    setNumericValueIfIdle(deviceQnhInput, ownship.device_qnh_hpa, 1);
    setNumericValueIfIdle(deviceAltitudeInput, ownship.device_altitude_m ?? ownship.gps_altitude_m, 0);
  }
  const wind = snapshot.wind || (state.runtime ? state.runtime.wind : null);
  if (wind) {
    setNumericValueIfIdle(windDirectionInput, wind.direction_deg, 1);
    setNumericValueIfIdle(windSpeedInput, wind.speed_kmh, 1);
  }
  const environment = state.runtime ? state.runtime.environment : null;
  if (environment) {
    setNumericValueIfIdle(oatInput, environment.oat_c, 1);
  }
  if (state.runtime && state.runtime.primary_device) {
    setSelectValueIfIdle(deviceSelect, state.runtime.primary_device);
  }
}

function setSelectValueIfIdle(node, value) {
  if (!value || document.activeElement === node) {
    return;
  }
  node.value = value;
}

function setNumericValueIfIdle(node, value, digits) {
  if (document.activeElement === node || value === null || value === undefined || Number.isNaN(Number(value))) {
    return;
  }
  node.value = Number(value).toFixed(digits);
}

function currentStaticPressureHpa() {
  const ownship = state.snapshot ? state.snapshot.ownship : null;
  if (ownship && ownship.static_pressure_hpa !== null && ownship.static_pressure_hpa !== undefined) {
    return Number(ownship.static_pressure_hpa);
  }
  const staticPressureHpa = numericValue(staticPressureInput);
  if (staticPressureHpa !== null && staticPressureHpa > 0) {
    return staticPressureHpa;
  }
  const qnhHpa = numericValue(deviceQnhInput);
  const altitudeM = numericValue(deviceAltitudeInput);
  if (qnhHpa === null || altitudeM === null || qnhHpa <= 0) {
    return null;
  }
  return staticPressureForAltitude(qnhHpa, altitudeM);
}

function altitudeForStaticPressure(qnhHpa, staticPressureHpa) {
  return (Math.pow(qnhHpa, BARO_K1) - Math.pow(staticPressureHpa, BARO_K1)) / BARO_K2;
}

function staticPressureForAltitude(qnhHpa, altitudeM) {
  const base = Math.pow(qnhHpa, BARO_K1) - BARO_K2 * altitudeM;
  if (base <= 0) {
    return null;
  }
  return Math.pow(base, 1 / BARO_K1);
}

function qnhForStaticPressure(staticPressureHpa, altitudeM) {
  const base = Math.pow(staticPressureHpa, BARO_K1) + BARO_K2 * altitudeM;
  return Math.pow(base, 1 / BARO_K1);
}

function syncAltitudeFromQnhInput() {
  const qnhHpa = numericValue(deviceQnhInput);
  const staticPressureHpa = currentStaticPressureHpa();
  if (qnhHpa === null || staticPressureHpa === null || qnhHpa <= 0 || staticPressureHpa <= 0) {
    return;
  }
  deviceAltitudeInput.value = altitudeForStaticPressure(qnhHpa, staticPressureHpa).toFixed(0);
}

function syncQnhFromAltitudeInput() {
  const altitudeM = numericValue(deviceAltitudeInput);
  const staticPressureHpa = currentStaticPressureHpa();
  if (altitudeM === null || staticPressureHpa === null || staticPressureHpa <= 0) {
    return;
  }
  deviceQnhInput.value = qnhForStaticPressure(staticPressureHpa, altitudeM).toFixed(1);
}

function renderState() {
  renderOwnship(state.snapshot ? state.snapshot.ownship : null);
  renderTraffic(state.snapshot ? state.snapshot.traffic : []);
  renderHealth(state.snapshot, state.runtime);
}

function renderBridgeStatus(payload) {
  bridgeStatusGrid.innerHTML = "";
  const nodes = payload && Array.isArray(payload.nodes) ? payload.nodes : [];
  if (nodes.length === 0) {
    const empty = document.createElement("p");
    empty.className = "bridge-empty";
    empty.textContent = "No bridge status returned.";
    bridgeStatusGrid.appendChild(empty);
    return;
  }
  for (const node of nodes) {
    bridgeStatusGrid.appendChild(buildBridgeStatusBlock(node));
  }
}

function buildBridgeStatusBlock(node) {
  const block = document.createElement("div");
  block.className = "bridge-status-block";

  const header = document.createElement("div");
  header.className = "bridge-status-block__header";
  const heading = document.createElement("h3");
  heading.textContent = `${String(node.id || "bridge").toUpperCase()} Bridge`;
  const pill = document.createElement("span");
  const ready = Boolean(node.ready);
  pill.className = `bridge-state ${ready ? "bridge-state--ok" : "bridge-state--idle"}`;
  pill.textContent = ready ? "Ready" : "Needs attention";
  header.appendChild(heading);
  header.appendChild(pill);

  const detailsButton = document.createElement("button");
  detailsButton.className = "ghost-button bridge-details-button";
  detailsButton.type = "button";
  detailsButton.textContent = "Details";
  detailsButton.addEventListener("click", () => openBridgeDetails(node));

  block.appendChild(header);
  block.appendChild(detailsButton);
  return block;
}

function openBridgeDetails(node) {
  bridgeDetailsTitle.textContent = `${String(node.id || "bridge").toUpperCase()} Bridge Details`;
  bridgeDetailsContent.innerHTML = "";
  const details = buildBridgeDetails(node);
  bridgeDetailsContent.appendChild(details);
  if (typeof bridgeDetailsDialog.showModal === "function") {
    bridgeDetailsDialog.showModal();
  } else {
    bridgeDetailsDialog.setAttribute("open", "");
  }
}

function buildBridgeDetails(node) {
  const details = document.createElement("dl");
  details.className = "bridge-status-details bridge-status-details--dialog";
  appendBridgeDetail(details, "Bridge Target", node.ssh_target || "-");
  appendBridgeDetail(details, "Ready", node.ready ? "yes" : "no");
  appendBridgeDetail(details, "Primary", node.primary_status || (node.primary_active ? "active" : "unknown"));
  appendBridgeDetail(details, "Primary Ready", node.primary_ready ? "yes" : "no");
  appendBridgeDetail(details, "Primary PTY", node.primary_pty_target || node.primary_serial_path || "-");
  appendBridgeDetail(details, "Primary TCP", node.primary_tcp_connected ? "connected" : "disconnected");
  appendBridgeDetail(details, "Primary Bytes", `${node.primary_bytes_tcp_to_pty ?? 0} rx / ${node.primary_bytes_pty_to_tcp ?? 0} tx`);
  appendBridgeDetail(details, "FLARM", node.flarm_status || (node.flarm_active ? "active" : "unknown"));
  appendBridgeDetail(details, "FLARM Ready", node.flarm_ready ? "yes" : "no");
  appendBridgeDetail(details, "FLARM PTY", node.flarm_pty_target || node.flarm_serial_path || "-");
  appendBridgeDetail(details, "FLARM TCP", node.flarm_tcp_connected ? "connected" : "disconnected");
  appendBridgeDetail(details, "FLARM Bytes", `${node.flarm_bytes_tcp_to_pty ?? 0} rx / ${node.flarm_bytes_pty_to_tcp ?? 0} tx`);
  appendBridgeDetail(details, "Return Code", node.returncode ?? node.action_returncode ?? "-");
  const actionFailed = Number(node.action_returncode ?? 0) !== 0;
  const statusFailed = Number(node.returncode ?? 0) !== 0;
  const bridgeError = node.primary_last_error || node.flarm_last_error || "";
  const errorText = actionFailed ? node.action_stderr : statusFailed ? node.stderr : bridgeError;
  if (errorText) {
    appendBridgeDetail(details, "Error", errorText);
  }
  const actionOutput = !actionFailed ? node.action_stdout || node.action_stderr : "";
  if (actionOutput) {
    appendBridgeDetail(details, "Action", actionOutput);
  }
  if (node.processes) {
    appendBridgeDetail(details, "Processes", node.processes);
  }
  return details;
}

function closeBridgeDetails() {
  if (typeof bridgeDetailsDialog.close === "function" && bridgeDetailsDialog.open) {
    bridgeDetailsDialog.close();
    return;
  }
  bridgeDetailsDialog.removeAttribute("open");
}

function appendBridgeDetail(details, label, value) {
  const wrapper = document.createElement("div");
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = String(value || "-");
  wrapper.appendChild(dt);
  wrapper.appendChild(dd);
  details.appendChild(wrapper);
}

function renderOwnship(ownship) {
  ownshipGrid.innerHTML = "";
  const rows = [
    ["Timestamp", ownship ? ownship.timestamp_utc : "-"],
    ["Phase", ownship ? ownship.phase : "-"],
    ["Track", ownship ? `${formatNumber(ownship.track_deg, 1)} deg` : "-"],
    ["Speed", ownship ? `${formatNumber(ownship.speed_kmh, 1)} km/h` : "-"],
    ["Vario", ownship ? `${formatNumber(ownship.vertical_speed_ms, 2)} m/s` : "-"],
    ["GPS Alt", ownship ? `${formatNumber(ownship.gps_altitude_m, 1)} m` : "-"],
    ["Device Alt", ownship ? `${formatNumber(ownship.device_altitude_m ?? ownship.gps_altitude_m, 1)} m` : "-"],
    ["Static Pressure", ownship ? `${formatNumber(ownship.static_pressure_hpa, 2)} hPa` : "-"],
    ["Device QNH", ownship ? `${formatNumber(ownship.device_qnh_hpa, 2)} hPa` : "-"],
    ["Latitude", ownship ? formatNumber(ownship.latitude_deg, 5) : "-"],
    ["Longitude", ownship ? formatNumber(ownship.longitude_deg, 5) : "-"],
    ["On Ground", ownship ? String(ownship.on_ground) : "-"],
  ];
  for (const [label, value] of rows) {
    ownshipGrid.appendChild(buildDatum(label, value));
  }
}

function renderTraffic(traffic) {
  trafficTableBody.innerHTML = "";
  if (!traffic || traffic.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    row.innerHTML = '<td colspan="8">No traffic contacts published.</td>';
    trafficTableBody.appendChild(row);
    return;
  }
  for (const contact of traffic) {
    const visibleAircraftId = contact.aircraft_id || contact.contact_id;
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${contact.contact_id}</td>
      <td>${visibleAircraftId}</td>
      <td>${formatNumber(contact.relative_north_m, 0)}</td>
      <td>${formatNumber(contact.relative_east_m, 0)}</td>
      <td>${formatNumber(contact.relative_altitude_m, 0)}</td>
      <td>${formatNumber(contact.track_deg, 0)}</td>
      <td>${formatNumber(contact.climb_ms, 1)}</td>
      <td>${contact.alarm_level}</td>
    `;
    trafficTableBody.appendChild(row);
  }
}

function renderHealth(snapshot, runtime) {
  healthGrid.innerHTML = "";
  const adapters = runtime && runtime.adapters ? runtime.adapters : {};
  const xcvarioAdapter = adapters.xcvario || null;
  const sxhawkAdapter = adapters.sxhawk || null;
  const flarmAdapter = adapters.flarm || null;
  const rows = [
    ["Runtime State", snapshot ? snapshot.runtime_state : "-"],
    ["Health", snapshot ? snapshot.health : "-"],
    ["Seed", snapshot ? snapshot.seed : "-"],
    ["Sim Time", snapshot ? `${formatNumber(snapshot.sim_time_s, 1)} s` : "-"],
    [
      "Wind",
      snapshot && snapshot.wind
        ? `${formatNumber(snapshot.wind.direction_deg, 1)} deg / ${formatNumber(snapshot.wind.speed_kmh, 1)} km/h`
        : "-",
    ],
    [
      "OAT",
      runtime && runtime.environment ? `${formatNumber(runtime.environment.oat_c, 1)} deg C` : "-",
    ],
    [
      "Traffic Mode",
      runtime && runtime.traffic_config
        ? `${runtime.traffic_config.contact_count} contacts / collision=${runtime.traffic_config.collision_course}`
        : "-",
    ],
    ["Session Started", runtime ? String(runtime.started) : "-"],
    ["Tick Count", runtime ? runtime.scheduler.tick_count : "-"],
    ["Last Jitter", runtime ? `${formatNumber(runtime.scheduler.last_jitter_s, 4)} s` : "-"],
    [
      "Primary Device",
      runtime ? runtime.primary_device : "-",
    ],
    [
      "Primary Rates",
      runtime && runtime.scheduler
        ? `GPS ${runtime.scheduler.gps_hz || "-"} Hz / baro ${runtime.scheduler.baro_hz || "-"} Hz`
        : "-",
    ],
    [
      "XCvario Adapter",
      xcvarioAdapter
        ? `${xcvarioAdapter.bound_port} / active=${Boolean(xcvarioAdapter.active)} / connected=${xcvarioAdapter.client_connected}`
        : "-",
    ],
    [
      "SxHAWK Adapter",
      sxhawkAdapter
        ? `${sxhawkAdapter.bound_port} / active=${Boolean(sxhawkAdapter.active)} / connected=${sxhawkAdapter.client_connected}`
        : "-",
    ],
    [
      "FLARM Adapter",
      flarmAdapter ? `${flarmAdapter.bound_port} / connected=${flarmAdapter.client_connected}` : "-",
    ],
  ];
  for (const [label, value] of rows) {
    healthGrid.appendChild(buildDatum(label, value));
  }
}

function buildDatum(label, value) {
  const wrapper = document.createElement("div");
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = String(value);
  wrapper.appendChild(dt);
  wrapper.appendChild(dd);
  return wrapper;
}

function formatNumber(value, digits) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(digits);
}

connectButton.addEventListener("click", () => {
  void connectPanel();
});

disconnectButton.addEventListener("click", () => {
  disconnectPanel();
});

refreshButton.addEventListener("click", () => {
  void fetchState({ syncControls: true }).catch((error) => showApiError(String(error.message || error)));
});

bridgeStartButton.addEventListener("click", () => {
  void requestBridge("start");
});

bridgeStopButton.addEventListener("click", () => {
  void requestBridge("stop");
});

bridgeRestartButton.addEventListener("click", () => {
  void requestBridge("restart");
});

bridgeStatusButton.addEventListener("click", () => {
  void requestBridge("status");
});

bridgeDetailsCloseButton.addEventListener("click", closeBridgeDetails);

bridgeDetailsDialog.addEventListener("click", (event) => {
  if (event.target === bridgeDetailsDialog) {
    closeBridgeDetails();
  }
});

applyDeviceButton.addEventListener("click", () => {
  void postCommand("/api/v1/simulation/device", {
    primary_device: deviceSelect.value,
  }, { syncControls: true });
});

startButton.addEventListener("click", () => {
  void postCommand("/api/v1/simulation/start");
});

pauseButton.addEventListener("click", () => {
  void postCommand("/api/v1/simulation/pause");
});

resetButton.addEventListener("click", () => {
  void postCommand("/api/v1/simulation/reset", null, { syncControls: true });
});

applyManualButton.addEventListener("click", () => {
  const phase = manualPhaseSelect.value;
  const payload = {
    phase,
  };
  const numericFields = [
    ["heading_deg", numericValue(manualHeadingInput)],
  ];
  if (phase !== "on_ground") {
    numericFields.push(["speed_kmh", numericValue(manualSpeedInput)]);
  }
  if (phase === "straight") {
    numericFields.push(["wysokosc", numericValue(manualBaroAltitudeInput)]);
  }
  if (phase === "circling_left" || phase === "circling_right") {
    numericFields.push(
      ["speed_min_kmh", numericValue(circlingSpeedMinInput)],
      ["speed_max_kmh", numericValue(circlingSpeedMaxInput)],
      ["turn_radius_m", numericValue(manualTurnRadiusInput)],
      ["climb_min_ms", numericValue(manualClimbMinInput)],
      ["climb_max_ms", numericValue(manualClimbMaxInput)],
    );
  }
  if (phase === "glider_launch") {
    numericFields.push(
      ["climb_min_ms", numericValue(manualClimbMinInput)],
      ["climb_max_ms", numericValue(manualClimbMaxInput)],
    );
  }
  if (phase === "sink" || phase === "glider_landing") {
    numericFields.push(["sink_ms", numericValue(manualSinkInput)]);
  }
  for (const [key, value] of numericFields) {
    if (value !== null) {
      payload[key] = value;
    }
  }
  void postCommand("/api/v1/simulation/manual-mode", payload);
});

applyWindButton.addEventListener("click", () => {
  void postCommand("/api/v1/simulation/wind", {
    direction_deg: numericValue(windDirectionInput) ?? 0,
    speed_kmh: numericValue(windSpeedInput) ?? 0,
  });
});

applyOatButton.addEventListener("click", () => {
  void postCommand("/api/v1/simulation/oat", {
    oat_c: numericValue(oatInput) ?? 18.0,
  }, { syncControls: true });
});

deviceQnhInput.addEventListener("input", () => {
  syncAltitudeFromQnhInput();
});

deviceAltitudeInput.addEventListener("input", () => {
  syncQnhFromAltitudeInput();
});

applyQnhButton.addEventListener("click", () => {
  void postCommand("/api/v1/simulation/altimeter", {
    qnh_hpa: numericValue(deviceQnhInput) ?? 1013.25,
  }, { syncControls: true });
});

applyDeviceAltitudeButton.addEventListener("click", () => {
  void postCommand("/api/v1/simulation/altimeter", {
    altitude_m: numericValue(deviceAltitudeInput) ?? 0,
  }, { syncControls: true });
});

applyTrafficButton.addEventListener("click", () => {
  void postCommand("/api/v1/simulation/traffic", {
    enabled: trafficEnabledInput.checked,
    contact_count: Number(trafficCountInput.value || "0"),
    collision_course: trafficCollisionInput.checked,
  });
});

loadStoredSettings();
renderState();
