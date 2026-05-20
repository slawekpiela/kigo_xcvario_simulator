const STORAGE_RUNTIME_URL = "kigo.sim.runtimeUrl";
const STORAGE_RUNTIME_TOKEN = "kigo.sim.runtimeToken";
const STORAGE_BRIDGE_PREFIX = "kigo.sim.bridge.";
const DEFAULT_RUNTIME_TOKEN = "kigo-sim-20260508";
const BARO_K1 = 0.190263;
const BARO_K2 = 8.417286e-5;
const BRIDGE_DEFAULTS = {
  primaryPort: "4353",
  flarmPort: "4354",
  piSshTarget: "admin@192.168.0.114",
  piIdentity: "/Users/slawekpiela/.ssh/kigo_pi",
  piSimulatorHost: "192.168.0.105",
  piWorkdir: "/home/admin/kigo_xcvario_simulator",
  vmSshTarget: "codex-vm",
  vmIdentity: "",
  vmSimulatorHost: "172.16.119.1",
  vmWorkdir: "/home/slawek/kigo_xcvario_simulator",
};

const runtimeUrlInput = document.getElementById("runtime-url-input");
const runtimeTokenInput = document.getElementById("runtime-token-input");
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
const streamGrid = document.getElementById("stream-grid");
const bridgePrimaryPortInput = document.getElementById("bridge-primary-port-input");
const bridgeFlarmPortInput = document.getElementById("bridge-flarm-port-input");
const piBridgeSshTargetInput = document.getElementById("pi-bridge-ssh-target-input");
const piBridgeIdentityInput = document.getElementById("pi-bridge-identity-input");
const piBridgeSimulatorHostInput = document.getElementById("pi-bridge-simulator-host-input");
const piBridgeWorkdirInput = document.getElementById("pi-bridge-workdir-input");
const vmBridgeSshTargetInput = document.getElementById("vm-bridge-ssh-target-input");
const vmBridgeIdentityInput = document.getElementById("vm-bridge-identity-input");
const vmBridgeSimulatorHostInput = document.getElementById("vm-bridge-simulator-host-input");
const vmBridgeWorkdirInput = document.getElementById("vm-bridge-workdir-input");
const bridgeStartButton = document.getElementById("bridge-start-button");
const bridgeStopButton = document.getElementById("bridge-stop-button");
const bridgeRestartButton = document.getElementById("bridge-restart-button");
const bridgeStatusButton = document.getElementById("bridge-status-button");
const bridgeErrorNode = document.getElementById("bridge-error");
const bridgeStatusGrid = document.getElementById("bridge-status-grid");

const state = {
  runtimeUrl: "",
  token: "",
  streamAbortController: null,
  connected: false,
  snapshot: null,
  runtime: null,
};

function loadStoredSettings() {
  runtimeUrlInput.value = localStorage.getItem(STORAGE_RUNTIME_URL) || "http://127.0.0.1:8181";
  runtimeTokenInput.value = localStorage.getItem(STORAGE_RUNTIME_TOKEN) || DEFAULT_RUNTIME_TOKEN;
  loadStoredInput(bridgePrimaryPortInput, "primaryPort", BRIDGE_DEFAULTS.primaryPort);
  loadStoredInput(bridgeFlarmPortInput, "flarmPort", BRIDGE_DEFAULTS.flarmPort);
  loadStoredInput(piBridgeSshTargetInput, "piSshTarget", BRIDGE_DEFAULTS.piSshTarget);
  loadStoredInput(piBridgeIdentityInput, "piIdentity", BRIDGE_DEFAULTS.piIdentity);
  loadStoredInput(piBridgeSimulatorHostInput, "piSimulatorHost", BRIDGE_DEFAULTS.piSimulatorHost);
  loadStoredInput(piBridgeWorkdirInput, "piWorkdir", BRIDGE_DEFAULTS.piWorkdir);
  loadStoredInput(vmBridgeSshTargetInput, "vmSshTarget", BRIDGE_DEFAULTS.vmSshTarget);
  loadStoredInput(vmBridgeIdentityInput, "vmIdentity", BRIDGE_DEFAULTS.vmIdentity);
  loadStoredInput(vmBridgeSimulatorHostInput, "vmSimulatorHost", BRIDGE_DEFAULTS.vmSimulatorHost);
  loadStoredInput(vmBridgeWorkdirInput, "vmWorkdir", BRIDGE_DEFAULTS.vmWorkdir);
}

function persistSettings() {
  localStorage.setItem(STORAGE_RUNTIME_URL, runtimeUrlInput.value.trim());
  localStorage.setItem(STORAGE_RUNTIME_TOKEN, runtimeTokenInput.value);
  persistInput(bridgePrimaryPortInput, "primaryPort");
  persistInput(bridgeFlarmPortInput, "flarmPort");
  persistInput(piBridgeSshTargetInput, "piSshTarget");
  persistInput(piBridgeIdentityInput, "piIdentity");
  persistInput(piBridgeSimulatorHostInput, "piSimulatorHost");
  persistInput(piBridgeWorkdirInput, "piWorkdir");
  persistInput(vmBridgeSshTargetInput, "vmSshTarget");
  persistInput(vmBridgeIdentityInput, "vmIdentity");
  persistInput(vmBridgeSimulatorHostInput, "vmSimulatorHost");
  persistInput(vmBridgeWorkdirInput, "vmWorkdir");
}

function normalizeRuntimeUrl(rawValue) {
  const trimmed = String(rawValue || "").trim();
  return trimmed.replace(/\/+$/, "");
}

function loadStoredInput(node, key, defaultValue) {
  node.value = localStorage.getItem(`${STORAGE_BRIDGE_PREFIX}${key}`) || defaultValue;
}

function persistInput(node, key) {
  localStorage.setItem(`${STORAGE_BRIDGE_PREFIX}${key}`, node.value.trim());
}

function syncRuntimeSettingsFromInputs() {
  persistSettings();
  state.runtimeUrl = normalizeRuntimeUrl(runtimeUrlInput.value);
  state.token = runtimeTokenInput.value;
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
  const headers = {
    "X-Simulator-Token": state.token,
  };
  if (includeJson) {
    headers["Content-Type"] = "application/json";
  }
  return headers;
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${state.runtimeUrl}${path}`, {
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
  return response.json();
}

async function readErrorMessage(response) {
  const body = await response.text();
  if (!body) {
    return "";
  }
  try {
    const payload = JSON.parse(body);
    return payload.message || payload.error || body;
  } catch (_error) {
    return body;
  }
}

async function connectPanel() {
  syncRuntimeSettingsFromInputs();
  disconnectPanel();
  try {
    await fetchState({ syncControls: true });
    await openEventStream();
    state.connected = true;
    setStatus("ok", `Panel API connected to ${state.runtimeUrl}`);
    showApiError("");
  } catch (error) {
    state.connected = false;
    setStatus("error", `Failed to connect to ${state.runtimeUrl}`);
    showApiError(String(error.message || error));
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
  if (!state.runtimeUrl || !state.token) {
    showBridgeError("Runtime URL and simulator token are required.");
    return;
  }
  try {
    const payload = await requestJson(`/api/v1/bridges/${action}`, {
      method: "POST",
      body: JSON.stringify(buildBridgePayload()),
    });
    renderBridgeStatus(payload);
    if (action !== "status") {
      window.setTimeout(() => {
        void fetchState().catch(() => undefined);
      }, 1000);
    }
  } catch (error) {
    showBridgeError(String(error.message || error));
  }
}

function buildBridgePayload() {
  const payload = {
    primary_port: bridgePortValue(bridgePrimaryPortInput, 4353),
    flarm_port: bridgePortValue(bridgeFlarmPortInput, 4354),
    nodes: [
      bridgeNodeFromInputs(
        "pi",
        piBridgeSshTargetInput,
        piBridgeIdentityInput,
        piBridgeSimulatorHostInput,
        piBridgeWorkdirInput,
      ),
      bridgeNodeFromInputs(
        "vm",
        vmBridgeSshTargetInput,
        vmBridgeIdentityInput,
        vmBridgeSimulatorHostInput,
        vmBridgeWorkdirInput,
      ),
    ].filter((node) => node.ssh_target && node.simulator_host && node.workdir),
  };
  if (payload.nodes.length === 0) {
    throw new Error("At least one bridge target is required.");
  }
  return payload;
}

function bridgeNodeFromInputs(id, sshTargetInput, identityInput, simulatorHostInput, workdirInput) {
  return {
    id,
    ssh_target: sshTargetInput.value.trim(),
    identity_file: identityInput.value.trim(),
    simulator_host: simulatorHostInput.value.trim(),
    workdir: workdirInput.value.trim(),
  };
}

function bridgePortValue(node, defaultValue) {
  const port = Number(node.value || defaultValue);
  if (!Number.isInteger(port) || port <= 0 || port > 65535) {
    throw new Error("Bridge ports must be integers between 1 and 65535.");
  }
  return port;
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
  renderStreams(state.runtime);
  renderOwnship(state.snapshot ? state.snapshot.ownship : null);
  renderTraffic(state.snapshot ? state.snapshot.traffic : []);
  renderHealth(state.snapshot, state.runtime);
}

function renderStreams(runtime) {
  streamGrid.innerHTML = "";
  const adapters = runtime && runtime.adapters ? runtime.adapters : {};
  const primaryDevice = runtime && runtime.primary_device === "sxhawk" ? "sxhawk" : "xcvario";
  const primaryAdapter = adapters[primaryDevice] || null;
  const flarmAdapter = adapters.flarm || null;
  const streams = [
    {
      title: "Primary Stream",
      protocol: primaryDevice === "sxhawk" ? "SxHAWK" : "XCvario",
      adapter: primaryAdapter,
    },
    {
      title: "FLARM Stream",
      protocol: "FLARM",
      adapter: flarmAdapter,
    },
  ];
  for (const stream of streams) {
    streamGrid.appendChild(buildStreamBlock(stream));
  }
}

function buildStreamBlock({ title, protocol, adapter }) {
  const block = document.createElement("div");
  block.className = "stream-block";

  const header = document.createElement("div");
  header.className = "stream-block__header";
  const heading = document.createElement("h3");
  heading.textContent = title;
  const count = document.createElement("span");
  count.className = "stream-count";
  count.textContent = `${adapter ? adapter.client_count || 0 : 0} clients`;
  header.appendChild(heading);
  header.appendChild(count);

  const details = document.createElement("dl");
  details.className = "stream-details";
  appendStreamDetail(details, "Protocol", protocol);
  appendStreamDetail(details, "Port", adapter && adapter.bound_port ? adapter.bound_port : "-");
  appendStreamDetail(details, "Bridge Targets", streamConnectionValues(adapter, "local"));
  appendStreamDetail(details, "Connected Peers", streamConnectionValues(adapter, "peer"));

  block.appendChild(header);
  block.appendChild(details);
  return block;
}

function appendStreamDetail(details, label, value) {
  const wrapper = document.createElement("div");
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = Array.isArray(value) && value.length > 0 ? value.join(" / ") : String(value || "-");
  wrapper.appendChild(dt);
  wrapper.appendChild(dd);
  details.appendChild(wrapper);
}

function streamConnectionValues(adapter, key) {
  const connections = adapter && Array.isArray(adapter.client_connections) ? adapter.client_connections : [];
  const values = [];
  for (const connection of connections) {
    const value = connection && connection[key] ? String(connection[key]) : "";
    if (value && !values.includes(value)) {
      values.push(value);
    }
  }
  if (values.length > 0) {
    return values;
  }
  const clientCount = adapter && adapter.client_count ? adapter.client_count : 0;
  return clientCount > 0 ? [`${clientCount} connected`] : ["-"];
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
  const bothActive = Boolean(node.primary_active) && Boolean(node.flarm_active);
  pill.className = `bridge-state ${bothActive ? "bridge-state--ok" : "bridge-state--idle"}`;
  pill.textContent = bothActive ? "Active" : "Needs attention";
  header.appendChild(heading);
  header.appendChild(pill);

  const details = document.createElement("dl");
  details.className = "stream-details";
  appendBridgeDetail(details, "SSH Target", node.ssh_target || "-");
  appendBridgeDetail(details, "Mac Host", node.simulator_host || "-");
  appendBridgeDetail(details, "Primary", node.primary_status || (node.primary_active ? "active" : "unknown"));
  appendBridgeDetail(details, "FLARM", node.flarm_status || (node.flarm_active ? "active" : "unknown"));
  appendBridgeDetail(details, "Return Code", node.returncode ?? node.action_returncode ?? "-");
  const actionFailed = Number(node.action_returncode ?? 0) !== 0;
  const statusFailed = Number(node.returncode ?? 0) !== 0;
  const errorText = actionFailed ? node.action_stderr : statusFailed ? node.stderr : "";
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

  block.appendChild(header);
  block.appendChild(details);
  return block;
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
  if (phase !== "glider_launch") {
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
