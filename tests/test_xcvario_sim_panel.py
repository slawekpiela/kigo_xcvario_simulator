import http.client
from pathlib import Path
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
            'value="slawek@172.16.119.135"',
            'id="pi-bridge-target-input"',
            'value="admin@192.168.0.114"',
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
            'id="circling-speed-min-input"',
            'id="circling-speed-max-input"',
            'id="apply-manual-button"',
            'id="start-button"',
            'id="pause-button"',
            'id="reset-button"',
            'id="apply-traffic-button"',
            'id="traffic-collision-input"',
            'id="ownship-grid"',
            'id="traffic-table-body"',
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
            'vmBridgeTarget: "slawek@172.16.119.135"',
            'vmRuntimeUrl: "http://172.16.119.135:8181"',
            'vmIdentity: "/Users/slawekpiela/.ssh/codex_debian_vm"',
            'vmSimulatorHost: "127.0.0.1"',
            'piBridgeTarget: "admin@192.168.0.114"',
            'piIdentity: "/home/slawek/.ssh/kigo_pi"',
            'piSimulatorHost: "172.16.119.135"',
            'piWorkdir: "/home/admin/kigo_xcvario_simulator"',
            "BRIDGE_DEFAULTS.vmIdentity",
            "BRIDGE_DEFAULTS.piIdentity",
            "isLegacyRuntimeUrl(storedRuntimeUrl)",
            "handleSseEvent(rawEvent)",
            "readErrorMessage(response)",
            "looksLikeHtml(body)",
            "runtimeUrlCandidates(state.runtimeUrl)",
            "controlApiRuntimeUrl(rawRuntimeUrl)",
            "syncRuntimeSettingsFromInputs();",
            'withPort(primary, "8181")',
            "Expected simulator JSON",
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
            import threading

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


if __name__ == "__main__":
    unittest.main()
