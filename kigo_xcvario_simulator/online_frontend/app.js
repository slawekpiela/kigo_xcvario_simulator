"use strict";
const SUPPORTED_LANGUAGES = new Set(["en", "pl", "de", "fr", "es", "cs", "sk"]);
const copy = {
  en: {pageTitle:"Kigo — online simulator",eyebrow:"KIGO / ONLINE SIMULATOR",heading:"Your test flight.",applicationId:"Kigo Application ID",applicationIdPlaceholder:"Enter the application ID",openSession:"Open session",setupHint:"To start, open Hardware → Devices and restart the devices by clicking Restart.",initialStatus:"Enter the ID, set the parameters and press Start.",flightData:"Flight data",altitude:"Altitude",speed:"Speed",flarmTraffic:"FLARM traffic",objects:"objects",flight:"Flight",mode:"Mode",straightFlight:"Straight flight",onGround:"On ground",gliderLaunch:"Glider launch",circlingLeft:"Circling left",circlingRight:"Circling right",sink:"Sink",landing:"Landing",speedKmh:"Speed (km/h)",altitudeM:"Altitude (m)",headingDeg:"Heading (°)",varioMin:"Vario min. (m/s)",varioMax:"Vario max. (m/s)",turnRadius:"Turn radius (m)",applyStart:"Apply and Start",pause:"Pause",resume:"Resume",wind:"Wind",directionDeg:"Direction (°)",setWind:"Set wind",objectCount:"Number of objects",motion:"Motion",circling:"Circling",collisionCourse:"Collision course",setFlarmTraffic:"Set FLARM traffic",startLocation:"Start location",airportOrPlace:"Airport ICAO or place",airportPlaceholder:"EPBA or Bielsko-Biała, Poland",locationHint:"Changing the location moves the simulated glider.",setLocation:"Set location",altimeter:"Altimeter",setQnh:"Set QNH",footer:"Each Application ID has a separate flight. The session expires after 5 minutes without a connected SIM device.",waiting:"waiting",connected:"connected",running:"Simulation running",paused:"Simulation paused",stopped:"Session ready — set the flight and press Start",sessionReady:"Session ready",invalidId:"Enter a valid Kigo Application ID.",requestError:"Connection error",retry:"Reconnecting shortly.",minMax:"Vario min. cannot be greater than max.",idOpen:"Enter the ID and open a session.",idInUse:"This Application ID is already in use. Enter a different Application ID."},
  pl: {pageTitle:"Kigo — symulator online",eyebrow:"KIGO / SYMULATOR ONLINE",heading:"Twój lot testowy.",applicationId:"Application ID z Kigo",applicationIdPlaceholder:"Wpisz ID aplikacji",openSession:"Otwórz sesję",setupHint:"Aby uruchomić, wejdź w Hardware → Devices i przestartuj urządzenia, klikając Restart.",initialStatus:"Wpisz ID, ustaw parametry i naciśnij Start.",flightData:"Dane lotu",altitude:"Wysokość",speed:"Prędkość",flarmTraffic:"Ruch FLARM",objects:"obiektów",flight:"Lot",mode:"Tryb",straightFlight:"Lot prosty",onGround:"Na ziemi",gliderLaunch:"Start szybowca",circlingLeft:"Krążenie w lewo",circlingRight:"Krążenie w prawo",sink:"Duszenie",landing:"Lądowanie",speedKmh:"Prędkość (km/h)",altitudeM:"Wysokość (m)",headingDeg:"Kurs (°)",varioMin:"Vario min. (m/s)",varioMax:"Vario maks. (m/s)",turnRadius:"Promień krążenia (m)",applyStart:"Zastosuj i Start",pause:"Pauza",resume:"Wznów",wind:"Wiatr",directionDeg:"Kierunek (°)",setWind:"Ustaw wiatr",objectCount:"Liczba obiektów",motion:"Ruch",circling:"Krążenie",collisionCourse:"Kurs kolizyjny",setFlarmTraffic:"Ustaw ruch FLARM",startLocation:"Miejsce startu",airportOrPlace:"Lotnisko ICAO lub miejscowość",airportPlaceholder:"EPBA lub Bielsko-Biała, Polska",locationHint:"Zmiana miejsca przestawia symulowany szybowiec.",setLocation:"Ustaw miejsce",altimeter:"Wysokościomierz",setQnh:"Ustaw QNH",footer:"Każde inne Application ID ma osobny lot. Sesja wygasa po 5 minutach bez połączonego urządzenia SIM.",waiting:"oczekiwanie",connected:"połączone",running:"Symulacja działa",paused:"Symulacja wstrzymana",stopped:"Sesja gotowa — ustaw lot i naciśnij Start",sessionReady:"Sesja gotowa",invalidId:"Wpisz poprawne Application ID z Kigo.",requestError:"Błąd połączenia",retry:"Ponowne połączenie za chwilę.",minMax:"Vario min. nie może być większe od maks.",idOpen:"Wpisz ID i otwórz sesję.",idInUse:"Ten Application ID jest już używany. Podaj inny Application ID."},
  de: {pageTitle:"Kigo — Online-Simulator",eyebrow:"KIGO / ONLINE-SIMULATOR",heading:"Dein Testflug.",applicationId:"Kigo Application ID",applicationIdPlaceholder:"Application ID eingeben",openSession:"Sitzung öffnen",setupHint:"Öffne zum Starten Hardware → Devices und starte die Geräte mit Restart neu.",initialStatus:"ID eingeben, Parameter einstellen und Start drücken.",flightData:"Flugdaten",altitude:"Höhe",speed:"Geschwindigkeit",flarmTraffic:"FLARM-Verkehr",objects:"Objekte",flight:"Flug",mode:"Modus",straightFlight:"Geradeausflug",onGround:"Am Boden",gliderLaunch:"Windenstart",circlingLeft:"Linkskreisen",circlingRight:"Rechtskreisen",sink:"Sinken",landing:"Landung",speedKmh:"Geschwindigkeit (km/h)",altitudeM:"Höhe (m)",headingDeg:"Kurs (°)",varioMin:"Vario min. (m/s)",varioMax:"Vario max. (m/s)",turnRadius:"Kreisradius (m)",applyStart:"Übernehmen und Start",pause:"Pause",resume:"Fortsetzen",wind:"Wind",directionDeg:"Richtung (°)",setWind:"Wind setzen",objectCount:"Anzahl Objekte",motion:"Bewegung",circling:"Kreisen",collisionCourse:"Kollisionskurs",setFlarmTraffic:"FLARM-Verkehr setzen",startLocation:"Startort",airportOrPlace:"Flugplatz-ICAO oder Ort",airportPlaceholder:"EDDM oder München, Deutschland",locationHint:"Ein neuer Ort versetzt das simulierte Segelflugzeug.",setLocation:"Ort setzen",altimeter:"Höhenmesser",setQnh:"QNH setzen",footer:"Jede Application ID hat einen eigenen Flug. Die Sitzung endet nach 5 Minuten ohne verbundenes SIM-Gerät.",waiting:"wartet",connected:"verbunden",running:"Simulation läuft",paused:"Simulation pausiert",stopped:"Sitzung bereit — Flug einstellen und Start drücken",sessionReady:"Sitzung bereit",invalidId:"Gültige Kigo Application ID eingeben.",requestError:"Verbindungsfehler",retry:"Erneuter Verbindungsversuch in Kürze.",minMax:"Vario min. darf nicht größer als max. sein.",idOpen:"ID eingeben und Sitzung öffnen."},
  fr: {pageTitle:"Kigo — simulateur en ligne",eyebrow:"KIGO / SIMULATEUR EN LIGNE",heading:"Votre vol d’essai.",applicationId:"Application ID Kigo",applicationIdPlaceholder:"Saisissez l’Application ID",openSession:"Ouvrir la session",setupHint:"Pour démarrer, ouvrez Hardware → Devices et redémarrez les appareils en cliquant sur Restart.",initialStatus:"Saisissez l’ID, réglez les paramètres et appuyez sur Démarrer.",flightData:"Données de vol",altitude:"Altitude",speed:"Vitesse",flarmTraffic:"Trafic FLARM",objects:"objets",flight:"Vol",mode:"Mode",straightFlight:"Vol rectiligne",onGround:"Au sol",gliderLaunch:"Décollage du planeur",circlingLeft:"Virage à gauche",circlingRight:"Virage à droite",sink:"Descente",landing:"Atterrissage",speedKmh:"Vitesse (km/h)",altitudeM:"Altitude (m)",headingDeg:"Cap (°)",varioMin:"Vario min. (m/s)",varioMax:"Vario max. (m/s)",turnRadius:"Rayon de virage (m)",applyStart:"Appliquer et démarrer",pause:"Pause",resume:"Reprendre",wind:"Vent",directionDeg:"Direction (°)",setWind:"Régler le vent",objectCount:"Nombre d’objets",motion:"Mouvement",circling:"Virage",collisionCourse:"Route de collision",setFlarmTraffic:"Régler le trafic FLARM",startLocation:"Lieu de départ",airportOrPlace:"ICAO de l’aérodrome ou localité",airportPlaceholder:"LFPG ou Paris, France",locationHint:"Changer le lieu déplace le planeur simulé.",setLocation:"Régler le lieu",altimeter:"Altimètre",setQnh:"Régler le QNH",footer:"Chaque Application ID possède son propre vol. La session expire après 5 minutes sans appareil SIM connecté.",waiting:"en attente",connected:"connecté",running:"Simulation en cours",paused:"Simulation en pause",stopped:"Session prête — réglez le vol et appuyez sur Démarrer",sessionReady:"Session prête",invalidId:"Saisissez une Application ID Kigo valide.",requestError:"Erreur de connexion",retry:"Nouvelle tentative dans un instant.",minMax:"Le vario min. ne peut pas dépasser le max.",idOpen:"Saisissez l’ID et ouvrez une session."},
  es: {pageTitle:"Kigo — simulador en línea",eyebrow:"KIGO / SIMULADOR EN LÍNEA",heading:"Tu vuelo de prueba.",applicationId:"Application ID de Kigo",applicationIdPlaceholder:"Introduce la Application ID",openSession:"Abrir sesión",setupHint:"Para iniciar, abre Hardware → Devices y reinicia los dispositivos pulsando Restart.",initialStatus:"Introduce la ID, ajusta los parámetros y pulsa Iniciar.",flightData:"Datos de vuelo",altitude:"Altitud",speed:"Velocidad",flarmTraffic:"Tráfico FLARM",objects:"objetos",flight:"Vuelo",mode:"Modo",straightFlight:"Vuelo recto",onGround:"En tierra",gliderLaunch:"Despegue del planeador",circlingLeft:"Viraje a la izquierda",circlingRight:"Viraje a la derecha",sink:"Descenso",landing:"Aterrizaje",speedKmh:"Velocidad (km/h)",altitudeM:"Altitud (m)",headingDeg:"Rumbo (°)",varioMin:"Vario mín. (m/s)",varioMax:"Vario máx. (m/s)",turnRadius:"Radio de viraje (m)",applyStart:"Aplicar e iniciar",pause:"Pausa",resume:"Reanudar",wind:"Viento",directionDeg:"Dirección (°)",setWind:"Ajustar viento",objectCount:"Número de objetos",motion:"Movimiento",circling:"Viraje",collisionCourse:"Rumbo de colisión",setFlarmTraffic:"Ajustar tráfico FLARM",startLocation:"Lugar de salida",airportOrPlace:"ICAO del aeródromo o localidad",airportPlaceholder:"LEMD o Madrid, España",locationHint:"Cambiar el lugar desplaza el planeador simulado.",setLocation:"Ajustar lugar",altimeter:"Altímetro",setQnh:"Ajustar QNH",footer:"Cada Application ID tiene un vuelo separado. La sesión caduca tras 5 minutos sin un dispositivo SIM conectado.",waiting:"en espera",connected:"conectado",running:"Simulación en marcha",paused:"Simulación en pausa",stopped:"Sesión lista — ajusta el vuelo y pulsa Iniciar",sessionReady:"Sesión lista",invalidId:"Introduce una Application ID de Kigo válida.",requestError:"Error de conexión",retry:"Se volverá a conectar en breve.",minMax:"El vario mín. no puede superar el máx.",idOpen:"Introduce la ID y abre una sesión."},
  cs: {pageTitle:"Kigo — online simulátor",eyebrow:"KIGO / ONLINE SIMULÁTOR",heading:"Váš zkušební let.",applicationId:"Application ID z Kigo",applicationIdPlaceholder:"Zadejte Application ID",openSession:"Otevřít relaci",setupHint:"Pro spuštění otevřete Hardware → Devices a restartujte zařízení kliknutím na Restart.",initialStatus:"Zadejte ID, nastavte parametry a stiskněte Start.",flightData:"Letová data",altitude:"Výška",speed:"Rychlost",flarmTraffic:"Provoz FLARM",objects:"objektů",flight:"Let",mode:"Režim",straightFlight:"Přímý let",onGround:"Na zemi",gliderLaunch:"Start kluzáku",circlingLeft:"Kroužení vlevo",circlingRight:"Kroužení vpravo",sink:"Klesání",landing:"Přistání",speedKmh:"Rychlost (km/h)",altitudeM:"Výška (m)",headingDeg:"Kurz (°)",varioMin:"Vario min. (m/s)",varioMax:"Vario max. (m/s)",turnRadius:"Poloměr kroužení (m)",applyStart:"Použít a spustit",pause:"Pauza",resume:"Pokračovat",wind:"Vítr",directionDeg:"Směr (°)",setWind:"Nastavit vítr",objectCount:"Počet objektů",motion:"Pohyb",circling:"Kroužení",collisionCourse:"Kolizní kurz",setFlarmTraffic:"Nastavit provoz FLARM",startLocation:"Místo startu",airportOrPlace:"ICAO letiště nebo místo",airportPlaceholder:"LKPR nebo Praha, Česko",locationHint:"Změna místa přesune simulovaný kluzák.",setLocation:"Nastavit místo",altimeter:"Výškoměr",setQnh:"Nastavit QNH",footer:"Každé Application ID má samostatný let. Relace vyprší po 5 minutách bez připojeného zařízení SIM.",waiting:"čeká",connected:"připojeno",running:"Simulace běží",paused:"Simulace pozastavena",stopped:"Relace připravena — nastavte let a stiskněte Start",sessionReady:"Relace připravena",invalidId:"Zadejte platné Application ID z Kigo.",requestError:"Chyba připojení",retry:"Brzy proběhne nové připojení.",minMax:"Vario min. nesmí být větší než max.",idOpen:"Zadejte ID a otevřete relaci."},
  sk: {pageTitle:"Kigo — online simulátor",eyebrow:"KIGO / ONLINE SIMULÁTOR",heading:"Váš skúšobný let.",applicationId:"Application ID z Kigo",applicationIdPlaceholder:"Zadajte Application ID",openSession:"Otvoriť reláciu",setupHint:"Na spustenie otvorte Hardware → Devices a reštartujte zariadenia kliknutím na Restart.",initialStatus:"Zadajte ID, nastavte parametre a stlačte Start.",flightData:"Letové údaje",altitude:"Výška",speed:"Rýchlosť",flarmTraffic:"Prevádzka FLARM",objects:"objektov",flight:"Let",mode:"Režim",straightFlight:"Priamy let",onGround:"Na zemi",gliderLaunch:"Štart vetroňa",circlingLeft:"Krúženie vľavo",circlingRight:"Krúženie vpravo",sink:"Klesanie",landing:"Pristátie",speedKmh:"Rýchlosť (km/h)",altitudeM:"Výška (m)",headingDeg:"Kurz (°)",varioMin:"Vario min. (m/s)",varioMax:"Vario max. (m/s)",turnRadius:"Polomer krúženia (m)",applyStart:"Použiť a spustiť",pause:"Pauza",resume:"Pokračovať",wind:"Vietor",directionDeg:"Smer (°)",setWind:"Nastaviť vietor",objectCount:"Počet objektov",motion:"Pohyb",circling:"Krúženie",collisionCourse:"Kolízny kurz",setFlarmTraffic:"Nastaviť prevádzku FLARM",startLocation:"Miesto štartu",airportOrPlace:"ICAO letiska alebo miesto",airportPlaceholder:"LZIB alebo Bratislava, Slovensko",locationHint:"Zmena miesta presunie simulovaný vetroň.",setLocation:"Nastaviť miesto",altimeter:"Výškomer",setQnh:"Nastaviť QNH",footer:"Každé Application ID má samostatný let. Relácia vyprší po 5 minútach bez pripojeného zariadenia SIM.",waiting:"čaká",connected:"pripojené",running:"Simulácia beží",paused:"Simulácia pozastavená",stopped:"Relácia pripravená — nastavte let a stlačte Start",sessionReady:"Relácia pripravená",invalidId:"Zadajte platné Application ID z Kigo.",requestError:"Chyba pripojenia",retry:"Čoskoro prebehne nové pripojenie.",minMax:"Vario min. nesmie byť väčšie ako max.",idOpen:"Zadajte ID a otvorte reláciu."}
};
Object.assign(copy.de, {idInUse:"Diese Application ID wird bereits verwendet. Gib eine andere Application ID ein."});
Object.assign(copy.fr, {idInUse:"Cette Application ID est déjà utilisée. Saisissez une autre Application ID."});
Object.assign(copy.es, {idInUse:"Esta Application ID ya está en uso. Introduce otra Application ID."});
Object.assign(copy.cs, {idInUse:"Toto Application ID se již používá. Zadejte jiné Application ID."});
Object.assign(copy.sk, {idInUse:"Toto Application ID sa už používa. Zadajte iné Application ID."});
Object.assign(copy.en, {rateLimited:"The simulator connection limit for this network or Application ID was reached. Wait a moment or use another ID."});
Object.assign(copy.pl, {rateLimited:"Osiągnięto limit połączeń symulatora dla tej sieci lub Application ID. Poczekaj chwilę albo użyj innego ID."});
Object.assign(copy.de, {rateLimited:"Das Verbindungslimit des Simulators für dieses Netzwerk oder diese Application ID ist erreicht. Warte kurz oder verwende eine andere ID."});
Object.assign(copy.fr, {rateLimited:"La limite de connexions du simulateur pour ce réseau ou cette Application ID est atteinte. Patientez ou utilisez un autre ID."});
Object.assign(copy.es, {rateLimited:"Se alcanzó el límite de conexiones del simulador para esta red o Application ID. Espera un momento o usa otra ID."});
Object.assign(copy.cs, {rateLimited:"Byl dosažen limit připojení simulátoru pro tuto síť nebo Application ID. Chvíli počkejte nebo použijte jiné ID."});
Object.assign(copy.sk, {rateLimited:"Bol dosiahnutý limit pripojení simulátora pre túto sieť alebo Application ID. Chvíľu počkajte alebo použite iné ID."});
const applicationIdHints = {
  en: "To set/retrieve your Application ID go to: CONFIGURATION -> GENERAL -> SERVICE -> APPLICATION ID",
  pl: "Aby ustawić/odczytać swój Application ID, przejdź do: CONFIGURATION -> GENERAL -> SERVICE -> APPLICATION ID",
  de: "Um deine Application ID festzulegen/abzurufen, gehe zu: CONFIGURATION -> GENERAL -> SERVICE -> APPLICATION ID",
  fr: "Pour définir/récupérer votre Application ID, allez dans : CONFIGURATION -> GENERAL -> SERVICE -> APPLICATION ID",
  es: "Para establecer/consultar tu Application ID, ve a: CONFIGURATION -> GENERAL -> SERVICE -> APPLICATION ID",
  cs: "Chcete-li nastavit/zjistit své Application ID, přejděte na: CONFIGURATION -> GENERAL -> SERVICE -> APPLICATION ID",
  sk: "Ak chcete nastaviť/získať svoje Application ID, prejdite na: CONFIGURATION -> GENERAL -> SERVICE -> APPLICATION ID"
};
for (const [code, hint] of Object.entries(applicationIdHints)) copy[code].applicationIdHint = hint;
let language = "en";
let deviceState = {vario: false, flarm: false};
function t(key) { return (copy[language] && copy[language][key]) || copy.en[key] || key; }
function renderDevices() {
  document.getElementById("devices").textContent = `Vario: ${deviceState.vario ? t("connected") : t("waiting")} · FLARM: ${deviceState.flarm ? t("connected") : t("waiting")}`;
}
function setLanguage(code) {
  language = SUPPORTED_LANGUAGES.has(code) ? code : "en";
  document.documentElement.lang = language;
  document.querySelectorAll("[data-i18n]").forEach(element => { element.textContent = t(element.dataset.i18n); });
  document.querySelectorAll("[data-i18n-html]").forEach(element => { element.innerHTML = t(element.dataset.i18nHtml); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(element => { element.placeholder = t(element.dataset.i18nPlaceholder); });
  document.querySelectorAll("[data-i18n-aria-label]").forEach(element => { element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel)); });
  document.title = t("pageTitle");
  renderDevices();
}
const queryLanguage = new URLSearchParams(window.location.search).get("interface_language") || new URLSearchParams(window.location.search).get("lang") || "en";
setLanguage(queryLanguage.toLowerCase().split("-")[0]);
window.addEventListener("message", event => {
  if (event.origin !== "https://kigoconcept.pl" && event.origin !== "https://www.kigoconcept.pl") return;
  if (event.data && event.data.type === "kigo-simulator-language") setLanguage(String(event.data.language || event.data.lang || "en").toLowerCase().split("-")[0]);
  if (event.data && event.data.type === "kigo-simulator-close") closeSession();
});
const idInput = document.getElementById("application-id");
const statusLine = document.getElementById("status");
let activeID = "", activeSessionID = "", busy = false, timer = null;
idInput.value = localStorage.getItem("kigo.sim.applicationId") || "";

function createPanelClient() {
  const storageKey = "kigo.sim.panelClient";
  try {
    const existing = sessionStorage.getItem(storageKey);
    if (/^[a-f0-9]{32}$/.test(existing || "")) return existing;
  } catch (_) {}
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const value = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
  try { sessionStorage.setItem(storageKey, value); } catch (_) {}
  return value;
}

const panelClient = createPanelClient();

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
      body: JSON.stringify({application_id: id, panel_client: panelClient, ...body}), signal: controller.signal
    });
    const value = await response.json();
    if (!response.ok) {
      const message = response.status === 409 && path === "session" ? t("idInUse") :
        response.status === 429 ? t("rateLimited") : value.error || `${t("requestError")} (${response.status})`;
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return value;
  } finally { clearTimeout(timeout); }
}

async function connect() {
  const id = idInput.value.trim();
  if (!/^[A-Za-z0-9_.-]{1,64}$/.test(id)) throw new Error(t("invalidId"));
  if (activeID === id && activeSessionID) return;
  if (activeID && activeID !== id) closeSession();
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
  const body = JSON.stringify({application_id: applicationID, session_id: sessionID, panel_client: panelClient});
  const beacon = new Blob([body], {type: "application/json"});
  if (!navigator.sendBeacon("/simulator/api/close", beacon)) {
    void fetch("/simulator/api/close", {
      method: "POST", headers: {"Content-Type": "application/json"}, body, keepalive: true
    });
  }
}

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
  deviceState = devices;
  renderDevices();
  const states = {running: t("running"), paused: t("paused"), stopped: t("stopped")};
  status(states[snapshot.runtime_state] || t("sessionReady"));
}

function schedule() {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    if (!busy && activeID && !document.hidden) {
      try { await refresh(); }
      catch (error) {
        if (error.status === 404) { activeID = ""; activeSessionID = ""; }
        status(`${error.message} ${t("retry")}`, true);
      }
    }
    schedule();
  }, 2000);
}

async function run(action) {
  if (busy) return;
  busy = true;
  idInput.disabled = true;
  document.querySelectorAll("button").forEach(button => button.disabled = true);
  try {
    await connect();
    try { await action(); await refresh(); }
    catch (error) {
      if (error.status !== 404) throw error;
      activeID = "";
      activeSessionID = "";
      await connect();
      await action();
      await refresh();
    }
  }
  catch (error) { status(error.message, true); }
  finally { busy = false; idInput.disabled = false; document.querySelectorAll("button").forEach(button => button.disabled = false); schedule(); }
}

document.getElementById("connect").addEventListener("click", () => run(async () => {}));
document.getElementById("flight").addEventListener("submit", event => {
  event.preventDefault();
  run(async () => {
    const parameters = values(event.target);
    if (parameters.climb_min_ms > parameters.climb_max_ms) throw new Error(t("minMax"));
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
  deviceState = {vario: false, flarm: false};
  renderDevices();
  status(t("idOpen"));
});
window.addEventListener("pagehide", event => {
  if (!event.persisted) closeSession();
});
schedule();
