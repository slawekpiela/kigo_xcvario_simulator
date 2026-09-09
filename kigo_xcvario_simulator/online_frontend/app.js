"use strict";
const idInput = document.getElementById("application-id");
const statusLine = document.getElementById("status");
let activeID = "", activeSessionID = "", busy = false, timer = null;
idInput.value = localStorage.getItem("kigo.sim.applicationId") || "";

function status(text, error = false) {
  statusLine.textContent = text;
  statusLine.classList.toggle("error", error);
}

async function request(path, body, id = activeID) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(`/simulator/api/${path}`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({application_id: id, ...body}), signal: controller.signal
    });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || `Błąd połączenia (${response.status})`);
    return value;
  } finally { clearTimeout(timeout); }
}

async function connect() {
  const id = idInput.value.trim();
  if (!/^[A-Za-z0-9_.-]{1,64}$/.test(id)) throw new Error("Wpisz poprawne Application ID z Kigo.");
  // Explicit actions can recreate an expired session; background polling cannot.
  const session = await request("session", {}, id);
  activeID = id;
  activeSessionID = session.session_id;
  localStorage.setItem("kigo.sim.applicationId", id);
}

function closeSession() {
  const applicationID = activeID;
  const sessionID = activeSessionID;
  activeID = "";
  activeSessionID = "";
  clearTimeout(timer);
  if (!applicationID || !sessionID) return;
  const body = JSON.stringify({application_id: applicationID, session_id: sessionID});
  const beacon = new Blob([body], {type: "application/json"});
  if (!navigator.sendBeacon("/simulator/api/close", beacon)) {
    void fetch("/simulator/api/close", {
      method: "POST", headers: {"Content-Type": "application/json"}, body, keepalive: true
    });
  }
}

window.addEventListener("message", event => {
  const trustedParent = event.origin === "https://kigoconcept.pl" ||
    event.origin === "https://www.kigoconcept.pl";
  if (trustedParent && event.data && event.data.type === "kigo-simulator-close") {
    closeSession();
  }
});

async function control(action, parameters = {}) {
  return request("control", {action, parameters});
}

function values(form) {
  const result = {};
  for (const input of form.elements) {
    if (!input.name) continue;
    result[input.name] = input.type === "checkbox" ? input.checked :
      input.type === "number" ? Number(input.value) : input.value;
  }
  return result;
}

async function refresh() {
  if (!activeID) return;
  const refreshedID = activeID;
  const {snapshot, devices} = await control("state");
  if (activeID !== refreshedID) return;
  const own = snapshot.ownship;
  document.getElementById("altitude").textContent = Math.round(own.gps_altitude_m);
  document.getElementById("speed").textContent = Math.round(own.speed_kmh);
  document.getElementById("vario").textContent = own.vertical_speed_ms.toFixed(1);
  document.getElementById("contacts").textContent = snapshot.traffic.length;
  document.getElementById("devices").textContent = `Vario: ${devices.vario ? "połączone" : "oczekiwanie"} · FLARM: ${devices.flarm ? "połączone" : "oczekiwanie"}`;
  const states = {running: "Symulacja działa", paused: "Symulacja wstrzymana", stopped: "Sesja gotowa — ustaw lot i naciśnij Start"};
  status(states[snapshot.runtime_state] || "Sesja gotowa");
}

function schedule() {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    if (!busy && activeID && !document.hidden) {
      try { await refresh(); }
      catch (error) { status(`${error.message} Ponowne połączenie za chwilę.`, true); }
    }
    schedule();
  }, 2000);
}

async function run(action) {
  if (busy) return;
  busy = true;
  idInput.disabled = true;
  document.querySelectorAll("button").forEach(button => button.disabled = true);
  try { await connect(); await action(); await refresh(); }
  catch (error) { status(error.message, true); }
  finally { busy = false; idInput.disabled = false; document.querySelectorAll("button").forEach(button => button.disabled = false); schedule(); }
}

document.getElementById("connect").addEventListener("click", () => run(async () => {}));
document.getElementById("flight").addEventListener("submit", event => {
  event.preventDefault();
  run(async () => {
    const parameters = values(event.target);
    if (parameters.climb_min_ms > parameters.climb_max_ms) throw new Error("Vario min. nie może być większe od maks.");
    await control("manual-mode", parameters);
    await control("start");
  });
});
for (const [formID, action] of [["wind", "wind"], ["traffic", "traffic"], ["airport", "start-airport"], ["altimeter", "altimeter"]]) {
  document.getElementById(formID).addEventListener("submit", event => {
    event.preventDefault();
    run(async () => {
      const parameters = values(event.target);
      if (formID === "traffic") Object.assign(parameters, {enabled: parameters.contact_count > 0, reset: true});
      await control(action, parameters);
    });
  });
}
document.getElementById("pause").addEventListener("click", () => run(() => control("pause")));
document.getElementById("resume").addEventListener("click", () => run(() => control("start")));
idInput.addEventListener("input", () => {
  closeSession();
  if (!idInput.value.trim()) localStorage.removeItem("kigo.sim.applicationId");
  for (const id of ["altitude", "speed", "vario", "contacts"])
    document.getElementById(id).textContent = "—";
  document.getElementById("devices").textContent = "Vario: oczekiwanie · FLARM: oczekiwanie";
  status("Wpisz ID i otwórz sesję.");
});
window.addEventListener("pagehide", event => {
  if (!event.persisted) closeSession();
});
schedule();
