import http.client
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch

from kigo_xcvario_simulator.panel.start_frontend import _android_bridge_status_payload, build_frontend_server


class SimulatorPanelAssetsTests(unittest.TestCase):
    def test_frontend_html_exposes_connection_manual_mode_and_health_hooks(self):
        html = Path("kigo_xcvario_simulator/panel/frontend/index.html").read_text(encoding="utf-8")

        for snippet in (
            'id="runtime-url-input"',
            'id="device-select"',
            '<option value="sxhawk">SxHAWK</option>',
            'id="start-airport-icao-input"',
            "Start airport or place",
            'placeholder="KMEV or Minden Tahoe USA"',
            'id="apply-device-button"',
            "<h2>Bridge Control</h2>",
            'id="vm-bridge-target-input"',
            'value="slawek@172.16.119.137"',
            'id="pi-bridge-target-input"',
            'value="admin@192.168.0.106"',
            'id="bridge-start-button"',
            'id="bridge-stop-button"',
            'id="bridge-restart-button"',
            'id="bridge-status-button"',
            'id="phone-bridge-status-grid"',
            'id="bridge-status-grid"',
            'id="bridge-details-dialog"',
            'id="bridge-details-title"',
            'id="bridge-details-close-button"',
            'id="bridge-details-content"',
            "<h2>Manual Mode</h2>",
            '<option value="on_ground" selected>on_ground</option>',
            'id="manual-baro-altitude-input"',
            'id="manual-heading-input" type="number" step="0.1" value="135"',
            'id="manual-speed-input" type="number" step="0.1" value="95"',
            'id="manual-climb-min-input" type="number" step="0.1"',
            'id="manual-climb-max-input" type="number" step="0.1"',
            "Flight Altitude [m]",
            "<h2>Atmosphere</h2>",
            'id="wind-direction-input"',
            'id="wind-speed-input"',
            'id="apply-wind-button"',
            'id="oat-input"',
            'id="apply-oat-button"',
            "OAT [deg C]",
            'id="device-qnh-input"',
            'id="device-altitude-input"',
            'id="apply-qnh-button"',
            'id="apply-device-altitude-button"',
            "QNH [hPa]",
            "Device Altitude [m]",
            'id="static-pressure-input"',
            "Static Pressure [hPa]",
            'id="cpu-chart-button"',
            'href="/cpu-chart.html"',
            'id="circling-speed-min-input"',
            'id="circling-speed-max-input"',
            'id="apply-manual-button"',
            'id="start-button"',
            'id="pause-button"',
            'id="reset-button"',
            'id="traffic-motion-toggle-button"',
            "Traffic: Orbiting",
            'id="apply-traffic-button"',
            'id="traffic-count-input" type="number" min="0" max="29" step="1" value="29"',
            'id="traffic-circling-radius-min-input" type="number" min="100" max="12000" step="10" value="100"',
            'id="traffic-circling-radius-max-input" type="number" min="100" max="12000" step="10" value="700"',
            'id="traffic-collision-input"',
            'id="ownship-grid"',
            'id="traffic-table-body"',
            "<th>ID</th>",
            "<th>CALL SIGN</th>",
            "<th>Distance [m]</th>",
            "<th>Vertical [m/s]</th>",
            "<th>Speed [m/s]</th>",
            "<th>Registration</th>",
            'id="health-grid"',
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, html)
        for removed_snippet in (
            "<h2>Scenario</h2>",
            "<h2>Runtime</h2>",
            'id="preset-select"',
            'id="load-preset-button"',
            'id="theme-toggle-input"',
            'aria-label="Dark mode"',
            'id="runtime-token-input"',
            "<h2>Stream Links</h2>",
            'id="stream-grid"',
            'id="bridge-primary-port-input"',
            'id="bridge-flarm-port-input"',
            'id="pi-bridge-ssh-target-input"',
            'id="pi-bridge-identity-input"',
            'id="pi-bridge-simulator-host-input"',
            'id="pi-bridge-workdir-input"',
            'id="vm-bridge-ssh-target-input"',
            'id="vm-bridge-identity-input"',
            'id="vm-bridge-simulator-host-input"',
            'id="vm-bridge-workdir-input"',
            'id="manual-climb-min-input" type="number" step="0.1" value=',
            'id="manual-climb-max-input" type="number" step="0.1" value=',
        ):
            with self.subTest(removed_snippet=removed_snippet):
                self.assertNotIn(removed_snippet, html)

    def test_frontend_js_uses_state_endpoint_sse_and_control_commands(self):
        script = Path("kigo_xcvario_simulator/panel/frontend/app.js").read_text(encoding="utf-8")

        for snippet in (
            '"/api/v1/simulation/state"',
            "/api/v1/events",
            '"/api/v1/simulation/manual-mode"',
            '"/api/v1/simulation/wind"',
            '"/api/v1/simulation/oat"',
            '"/api/v1/simulation/altimeter"',
            '"/api/v1/simulation/traffic"',
            '"/api/v1/simulation/device"',
            '"/api/v1/simulation/start-airport"',
            '"/api/v1/simulation/start"',
            '"/api/v1/simulation/pause"',
            '"/api/v1/simulation/reset"',
            'void postCommand("/api/v1/simulation/manual-mode", payload);',
            "collision_course: trafficCollisionInput.checked",
            "circling_radius_min_m: numericValue(trafficCirclingRadiusMinInput)",
            "circling_radius_max_m: numericValue(trafficCirclingRadiusMaxInput)",
            "motion_mode: currentTrafficMotionMode()",
            "trafficMotionToggleButton.addEventListener",
            "payload.reset = true",
            "payload.start_airport_icao = startAirportIcao",
            "includeStartAirport: true",
            'const callSign = contact.competition_id || contact.registration || "-";',
            "const distanceM = Math.hypot(Number(contact.relative_north_m), Number(contact.relative_east_m));",
            "localStorage.setItem(STORAGE_RUNTIME_URL",
            "STORAGE_START_AIRPORT_ICAO",
            'vmBridgeTarget: "slawek@172.16.119.137"',
            'vmRuntimeUrl: "http://172.16.119.137:8181"',
            'vmIdentity: "/Users/slawekpiela/.ssh/codex_debian_vm"',
            'vmSimulatorHost: "127.0.0.1"',
            'piBridgeTarget: "admin@192.168.0.106"',
            'piIdentity: "/home/slawek/.ssh/kigo_pi"',
            'piSimulatorHost: "127.0.0.1"',
            'piWorkdir: "/home/admin/kigo_xcvario_simulator"',
            "BRIDGE_DEFAULTS.vmIdentity",
            "BRIDGE_DEFAULTS.piIdentity",
            "const nodes = [vmNode];",
            "if (piNode.ssh_target)",
            'throw new Error("VM bridge target is required.")',
            "reverse_tunnel: reverseTunnel",
            "isLegacyRuntimeUrl(storedRuntimeUrl)",
            "handleSseEvent(rawEvent)",
            "readErrorMessage(response)",
            "looksLikeHtml(body)",
            "runtimeUrlCandidates(state.runtimeUrl)",
            "controlApiRuntimeUrl(rawRuntimeUrl)",
            "defaultRuntimeUrlForPanel()",
            "isStaleRuntimeUrlForPanel(storedRuntimeUrl)",
            "isKnownStaleRuntimeUrl(storedUrl)",
            'url.hostname === "172.20.10.4"',
            "isPrivateNetworkHost(storedUrl.hostname)",
            "syncRuntimeSettingsFromInputs();",
            'withPort(primary, "8181")',
            "appendUnique(candidates, runtimeUrlFromPanelHost())",
            "appendUnique(candidates, defaultRuntimeUrlForPanel())",
            "Expected simulator JSON",
            "resetRuntimeToHomeOnConnect()",
            "normalizeStartAirportIcao(startAirportIcaoInput.value)",
            'body: JSON.stringify({\n        icao: startAirportIcao,',
            'requestJson("/api/v1/simulation/reset"',
            'phase: "on_ground"',
            'on_ground: true',
            'requestJson("/api/v1/simulation/start"',
            "restartBridgesAfterConnect()",
            'requestJson("/api/v1/bridges/restart"',
            "Bridges ready.",
            "bridge restart needs attention",
            "formatCommandError(path, error)",
            "async function postCommand(path, payload = null, { syncControls = false } = {})",
            "await fetchState({ syncControls });",
            'postCommand("/api/v1/simulation/reset", null, { syncControls: true })',
            'if (phase !== "on_ground")',
            '["speed_kmh", numericValue(manualSpeedInput)]',
            'if (phase === "straight")',
            '["wysokosc", numericValue(manualBaroAltitudeInput)]',
            'if (phase === "straight" || phase === "circling_left" || phase === "circling_right")',
            'if (phase === "circling_left" || phase === "circling_right")',
            '["speed_min_kmh", numericValue(circlingSpeedMinInput)]',
            '["speed_max_kmh", numericValue(circlingSpeedMaxInput)]',
            '["climb_min_ms", numericValue(manualClimbMinInput)]',
            '["climb_max_ms", numericValue(manualClimbMaxInput)]',
            'if (phase === "glider_launch")',
            'if (phase === "sink" || phase === "glider_landing")',
            '["sink_ms", numericValue(manualSinkInput)]',
            "direction_deg: numericValue(windDirectionInput) ?? 0",
            "speed_kmh: numericValue(windSpeedInput) ?? 0",
            "oat_c: numericValue(oatInput) ?? 18.0",
            "qnh_hpa: numericValue(deviceQnhInput) ?? 1013.25",
            "altitude_m: numericValue(deviceAltitudeInput) ?? 0",
            "setNumericValueIfIdle(staticPressureInput, ownship.static_pressure_hpa, 2)",
            "syncAltitudeFromQnhInput()",
            "syncQnhFromAltitudeInput()",
            "staticPressureForAltitude(qnhHpa, altitudeM)",
            "runtime.environment.oat_c",
            "runtime.primary_device",
            "adapters.sxhawk",
            "`/api/v1/bridges/${action}`",
            "buildBridgePayload()",
            "ready_timeout_s: BRIDGE_DEFAULTS.readyTimeoutS",
            "pollBridgeStatus(bridgePayload, action)",
            "bridgesReady(latest)",
            "bridgesStopped(latest)",
            "bridgeTimeoutMessage(action, latest)",
            '"/api/v1/android-bridge/status"',
            "renderPhoneBridgeStatus",
            'buildBridgeStatePill("Connected"',
            'buildBridgeStatePill("Transmitting"',
            "setBridgeBusy(true, action)",
            "vmBridgeTargetInput",
            "piBridgeTargetInput",
            'void requestBridge("start")',
            'void requestBridge("stop")',
            'void requestBridge("restart")',
            'void requestBridge("status")',
            "openBridgeDetails(node)",
            "buildBridgeDetails(node)",
            "bridgeDetailsDialog.showModal()",
            "closeBridgeDetails()",
            "Runtime does not support OAT yet.",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, script)
        for removed_snippet in (
            '"/api/v1/simulation/preset"',
            "buildPresetOverrides()",
            "presetSelect",
            'const STORAGE_THEME = "kigo.sim.theme";',
            'const STORAGE_RUNTIME_TOKEN = "kigo.sim.runtimeToken";',
            '"X-Simulator-Token"',
            "renderStreams(state.runtime)",
            "streamConnectionValues",
            "Bridge Targets",
            "Connected Peers",
            "document.documentElement.dataset.theme",
            "localStorage.setItem(STORAGE_THEME",
            "themeToggleInput",
            '"/api/v1/simulation/manual-mode", payload, { syncControls: true }',
        ):
            with self.subTest(removed_snippet=removed_snippet):
                self.assertNotIn(removed_snippet, script)

    def test_frontend_css_exposes_dark_only_theme_tokens(self):
        css = Path("kigo_xcvario_simulator/panel/frontend/style.css").read_text(encoding="utf-8")

        for snippet in (
            ":root {",
            "color-scheme: dark;",
            "--bg-start:",
            "--panel-border:",
            ".bridge-target-grid",
            ".bridge-dialog",
            ".bridge-details-button",
            ".bridge-status-details",
            ".bridge-status-grid",
            ".bridge-status-grid--phone",
            ".bridge-status-badges",
            ".bridge-state--ok",
            ".chart-shell",
            ".cpu-chart-canvas",
            ".chart-summary-grid",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, css)
        for removed_snippet in (
            ':root[data-theme="dark"]',
            ':root[data-theme="light"]',
            "color-scheme: light;",
            ".theme-toggle {",
            "--toggle-bg:",
            ".stream-grid",
            ".stream-details",
            ".bridge-form",
        ):
            with self.subTest(removed_snippet=removed_snippet):
                self.assertNotIn(removed_snippet, css)

    def test_frontend_server_serves_index_page(self):
        server = build_frontend_server(host="127.0.0.1", port=0)
        try:
            server_address = server.server_address

            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            connection = http.client.HTTPConnection(server_address[0], server_address[1], timeout=2.0)
            connection.request("GET", "/")
            response = connection.getresponse()
            payload = response.read().decode("utf-8")
            connection.close()

            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            self.assertIn("KIGO Vario Simulator Control Panel", payload)
        finally:
            server.shutdown()
            server.server_close()

    def test_frontend_server_serves_cpu_chart_page(self):
        server = build_frontend_server(host="127.0.0.1", port=0)
        try:
            server_address = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            connection = http.client.HTTPConnection(server_address[0], server_address[1], timeout=2.0)
            connection.request("GET", "/cpu-chart.html")
            response = connection.getresponse()
            payload = response.read().decode("utf-8")
            connection.close()

            self.assertEqual(response.status, 200)
            self.assertIn("CPU Temperature And Usage", payload)
            self.assertIn("/cpu-chart.js", payload)
            self.assertIn("Back To Panel", payload)
        finally:
            server.shutdown()
            server.server_close()

    def test_frontend_server_serves_cpu_log_json_from_local_file(self):
        old_local_file = os.environ.get("KIGO_CPU_LOG_LOCAL_FILE")
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "CPU_temperature"
            log_path.write_text(
                "\n".join(
                    [
                        "2026-05-22T00:00:00+02:00 cpu_temp_c=38.1 cpu_used_percent=2.5",
                        "2026-05-22T00:00:01+02:00 cpu_temp_c=39.2 cpu_used_percent=4.0",
                    ]
                ),
                encoding="utf-8",
            )
            os.environ["KIGO_CPU_LOG_LOCAL_FILE"] = str(log_path)
            server = build_frontend_server(host="127.0.0.1", port=0)
            try:
                server_address = server.server_address
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()

                connection = http.client.HTTPConnection(server_address[0], server_address[1], timeout=2.0)
                connection.request("GET", "/api/v1/pi/cpu-temperature-log?limit=1")
                response = connection.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
                connection.close()

                self.assertEqual(response.status, 200)
                self.assertEqual(payload["source"]["raw_lines"], 1)
                self.assertEqual(len(payload["records"]), 1)
                self.assertEqual(payload["records"][0]["timestamp"], "2026-05-22T00:00:01+02:00")
                self.assertEqual(payload["records"][0]["cpu_temp_c"], 39.2)
                self.assertEqual(payload["records"][0]["cpu_used_percent"], 4.0)
                self.assertEqual(payload["summary"]["sample_count"], 1)
            finally:
                server.shutdown()
                server.server_close()
                if old_local_file is None:
                    os.environ.pop("KIGO_CPU_LOG_LOCAL_FILE", None)
                else:
                    os.environ["KIGO_CPU_LOG_LOCAL_FILE"] = old_local_file

    def test_android_bridge_status_payload_reports_connected_phone(self):
        class FakeSocket:
            def close(self):
                return None

        def fake_run(command, **kwargs):
            if command[-2:] == ["devices", "-l"]:
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        "List of devices attached\n"
                        "R58M9050KLY device product:a50 model:SM-A505FN device:a50 transport_id:1\n"
                    ),
                    stderr="",
                )
            if command[-2:] == ["reverse", "--list"]:
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        "UsbFfs tcp:44353 tcp:4353\n"
                        "UsbFfs tcp:44354 tcp:4354\n"
                    ),
                    stderr="",
                )
            if command[-4:] == ["shell", "pm", "path", "pl.kigo.xcvario.bridge"]:
                return SimpleNamespace(returncode=0, stdout="package:/data/app/pl.kigo.xcvario.bridge/base.apk\n", stderr="")
            if command[-5:] == ["shell", "dumpsys", "activity", "services", "pl.kigo.xcvario.bridge"]:
                return SimpleNamespace(returncode=0, stdout="ServiceRecord pl.kigo.xcvario.bridge/.BridgeService\n", stderr="")
            if command[-3:] == ["shell", "ss", "-tn"]:
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        "ESTAB 0 0 127.0.0.1:4353 127.0.0.1:50100\n"
                        "ESTAB 0 0 127.0.0.1:44353 127.0.0.1:50101\n"
                        "ESTAB 0 0 127.0.0.1:4354 127.0.0.1:50102\n"
                        "ESTAB 0 0 127.0.0.1:44354 127.0.0.1:50103\n"
                    ),
                    stderr="",
                )
            if command[-3:] == ["shell", "ss", "-ltn"]:
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        "LISTEN 0 50 127.0.0.1:4353 0.0.0.0:*\n"
                        "LISTEN 0 50 127.0.0.1:4354 0.0.0.0:*\n"
                    ),
                    stderr="",
                )
            raise AssertionError(f"unexpected command: {command}")

        with (
            patch("kigo_xcvario_simulator.panel.start_frontend.subprocess.run", side_effect=fake_run),
            patch("kigo_xcvario_simulator.panel.start_frontend.socket.create_connection", return_value=FakeSocket()),
        ):
            payload = _android_bridge_status_payload()

        self.assertTrue(payload["connected"])
        self.assertTrue(payload["transmitting"])
        self.assertEqual(payload["device"]["serial"], "R58M9050KLY")
        self.assertTrue(payload["ports"]["primary"]["reverse"])
        self.assertTrue(payload["ports"]["flarm"]["mac_port_open"])


if __name__ == "__main__":
    unittest.main()
