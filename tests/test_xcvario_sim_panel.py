import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

from kigo_xcvario_simulator.panel.start_frontend import build_frontend_server


class SimulatorPanelAssetsTests(unittest.TestCase):
    def test_frontend_html_exposes_connection_manual_mode_and_health_hooks(self):
        html = Path("kigo_xcvario_simulator/panel/frontend/index.html").read_text(encoding="utf-8")

        for snippet in (
            'id="runtime-url-input"',
            'id="device-select"',
            '<option value="sxhawk">SxHAWK</option>',
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
            'id="apply-traffic-button"',
            'id="traffic-count-input" type="number" min="0" max="26"',
            'id="traffic-collision-input"',
            'id="ownship-grid"',
            'id="traffic-table-body"',
            "<th>FLARM ID</th>",
            "<th>CN</th>",
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
            '"/api/v1/simulation/start"',
            '"/api/v1/simulation/pause"',
            '"/api/v1/simulation/reset"',
            'void postCommand("/api/v1/simulation/manual-mode", payload);',
            "collision_course: trafficCollisionInput.checked",
            "localStorage.setItem(STORAGE_RUNTIME_URL",
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
            "reverse_tunnel: reverseTunnel",
            "isLegacyRuntimeUrl(storedRuntimeUrl)",
            "handleSseEvent(rawEvent)",
            "readErrorMessage(response)",
            "looksLikeHtml(body)",
            "runtimeUrlCandidates(state.runtimeUrl)",
            "controlApiRuntimeUrl(rawRuntimeUrl)",
            "defaultRuntimeUrlForPanel()",
            "isStaleRuntimeUrlForPanel(storedRuntimeUrl)",
            "syncRuntimeSettingsFromInputs();",
            'withPort(primary, "8181")',
            "Expected simulator JSON",
            "resetRuntimeToHomeOnConnect()",
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


if __name__ == "__main__":
    unittest.main()
