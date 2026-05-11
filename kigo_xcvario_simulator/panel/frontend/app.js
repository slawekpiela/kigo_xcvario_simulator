const STORAGE_RUNTIME_URL = "kigo.sim.runtimeUrl";
const STORAGE_RUNTIME_TOKEN = "kigo.sim.runtimeToken";

const runtimeUrlInput = document.getElementById("runtime-url-input");
const runtimeTokenInput = document.getElementById("runtime-token-input");
const connectButton = document.getElementById("connect-button");
const disconnectButton = document.getElementById("disconnect-button");
const refreshButton = document.getElementById("refresh-button");
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

const trafficEnabledInput = document.getElementById("traffic-enabled-input");
const trafficCountInput = document.getElementById("traffic-count-input");
const trafficCollisionInput = document.getElementById("traffic-collision-input");
const applyTrafficButton = document.getElementById("apply-traffic-button");

const ownshipGrid = document.getElementById("ownship-grid");
const trafficTableBody = document.getElementById("traffic-table-body");
const healthGrid = document.getElementById("health-grid");

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
  runtimeTokenInput.value = localStorage.getItem(STORAGE_RUNTIME_TOKEN) || "change-me-before-lab-use";
}

function persistSettings() {
  localStorage.setItem(STORAGE_RUNTIME_URL, runtimeUrlInput.value.trim());
  localStorage.setItem(STORAGE_RUNTIME_TOKEN, runtimeTokenInput.value);
}

function normalizeRuntimeUrl(rawValue) {
  const trimmed = String(rawValue || "").trim();
  return trimmed.replace(/\/+$/, "");
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
  persistSettings();
  state.runtimeUrl = normalizeRuntimeUrl(runtimeUrlInput.value);
  state.token = runtimeTokenInput.value;
  disconnectPanel();
  try {
    await fetchState({ syncControls: true });
    await openEventStream();
    state.connected = true;
    setStatus("ok", `Connected to ${state.runtimeUrl}`);
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

function formatCommandError(path, error) {
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

function renderState() {
  renderOwnship(state.snapshot ? state.snapshot.ownship : null);
  renderTraffic(state.snapshot ? state.snapshot.traffic : []);
  renderHealth(state.snapshot, state.runtime);
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
      "XCVario Rates",
      runtime && runtime.scheduler
        ? `GPS ${runtime.scheduler.gps_hz || "-"} Hz / baro ${runtime.scheduler.baro_hz || "-"} Hz`
        : "-",
    ],
    [
      "XCvario Adapter",
      runtime ? `${runtime.adapters.xcvario.bound_port} / connected=${runtime.adapters.xcvario.client_connected}` : "-",
    ],
    [
      "FLARM Adapter",
      runtime ? `${runtime.adapters.flarm.bound_port} / connected=${runtime.adapters.flarm.client_connected}` : "-",
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
  const payload = {
    phase: manualPhaseSelect.value,
  };
  const numericFields = [
    ["heading_deg", numericValue(manualHeadingInput)],
    ["speed_kmh", numericValue(manualSpeedInput)],
    ["wysokosc", numericValue(manualBaroAltitudeInput)],
    ["speed_min_kmh", numericValue(circlingSpeedMinInput)],
    ["speed_max_kmh", numericValue(circlingSpeedMaxInput)],
    ["turn_radius_m", numericValue(manualTurnRadiusInput)],
    ["climb_min_ms", numericValue(manualClimbMinInput)],
    ["climb_max_ms", numericValue(manualClimbMaxInput)],
    ["sink_ms", numericValue(manualSinkInput)],
  ];
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

applyTrafficButton.addEventListener("click", () => {
  void postCommand("/api/v1/simulation/traffic", {
    enabled: trafficEnabledInput.checked,
    contact_count: Number(trafficCountInput.value || "0"),
    collision_course: trafficCollisionInput.checked,
  });
});

loadStoredSettings();
renderState();
