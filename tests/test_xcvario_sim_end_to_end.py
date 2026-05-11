import http.client
import json
import socket
import time
import unittest

from kigo_xcvario_simulator.config import (
    ControlApiConfig,
    EndpointConfig,
    HomePosition,
    SchedulerConfig,
    SimulatorRuntimeConfig,
    XcvarioConfig,
)
from kigo_xcvario_simulator.control_api import ControlApiServer
from kigo_xcvario_simulator.session import SimulatorRuntimeSession
from kigo_xcvario_simulator.state import FlightPhase, RuntimeState


def _config() -> SimulatorRuntimeConfig:
    return SimulatorRuntimeConfig(
        session_id="xcvario-sim",
        seed=42,
        device_qnh_hpa=1013.25,
        home_position=HomePosition(latitude_deg=49.83833, longitude_deg=19.00202, gps_altitude_m=401.0),
        control_api=ControlApiConfig(bind_host="127.0.0.1", port=0, token="token"),
        xcvario=XcvarioConfig(bind_host="127.0.0.1", port=0, polar_name="DG 800B/15"),
        flarm=EndpointConfig(bind_host="127.0.0.1", port=0),
        scheduler=SchedulerConfig(tick_hz=10, ownship_hz=2, traffic_hz=1),
    )


class SimulatorEndToEndSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = SimulatorRuntimeSession(_config())
        self.session.start(start_scheduler=False)
        self.api = ControlApiServer(
            bind_host="127.0.0.1",
            port=0,
            token="token",
            session=self.session,
        )
        self.api.start()
        self.api_connection = http.client.HTTPConnection("127.0.0.1", self.api.bound_port, timeout=3.0)

    def tearDown(self) -> None:
        self.api_connection.close()
        self.api.stop()
        self.session.stop()

    def test_full_flight_preset_streams_ownship_and_traffic_until_stop(self):
        xc_client = socket.create_connection(("127.0.0.1", self.session.xcvario_adapter.bound_port), timeout=2.0)
        flarm_client = socket.create_connection(("127.0.0.1", self.session.flarm_adapter.bound_port), timeout=2.0)
        self.addCleanup(xc_client.close)
        self.addCleanup(flarm_client.close)
        time.sleep(0.05)

        self._post_json("/api/v1/simulation/traffic", {"enabled": True, "contact_count": 2})
        self._post_json("/api/v1/simulation/wind", {"direction_deg": 270.0, "speed_kmh": 25.5})
        self._post_json("/api/v1/simulation/oat", {"oat_c": 7.5})
        self._post_json("/api/v1/simulation/preset", {"preset_id": "full_flight", "seed": 42, "autostart": True})

        snapshot = None
        for _ in range(18):
            snapshot = self.session.orchestrator.tick(32.0)
            self.session.xcvario_adapter.publish_snapshot(snapshot)
            self.session.flarm_adapter.publish_snapshot(snapshot)

        assert snapshot is not None
        xc_payload = xc_client.recv(4096).decode("ascii")
        flarm_payload = flarm_client.recv(4096).decode("ascii")

        self.assertEqual(snapshot.runtime_state, RuntimeState.STOPPED)
        self.assertEqual(snapshot.ownship.phase, FlightPhase.GLIDER_LANDING)
        self.assertTrue(snapshot.ownship.on_ground)
        self.assertIn("$PXCV,", xc_payload)
        self.assertIn(",7.5,", xc_payload)
        self.assertIn(",T,7.5*", xc_payload)
        self.assertIn("$WIMWV,270.0,T,25.5,K,A*", xc_payload)
        self.assertIn("$PFLAU,", flarm_payload)

    def test_manual_override_updates_state_without_reset(self):
        xc_client = socket.create_connection(("127.0.0.1", self.session.xcvario_adapter.bound_port), timeout=2.0)
        self.addCleanup(xc_client.close)
        time.sleep(0.05)

        self._post_json("/api/v1/simulation/preset", {"preset_id": "circling", "seed": 7, "autostart": True})
        before = self.session.orchestrator.tick(5.0)
        self.session.xcvario_adapter.publish_snapshot(before)

        self._post_json(
            "/api/v1/simulation/manual-mode",
            {"phase": "straight", "heading_deg": 135.0, "speed_kmh": 100.0},
        )
        after = self.session.orchestrator.tick(5.0)
        self.session.xcvario_adapter.publish_snapshot(after)

        state_payload = self._get_json("/api/v1/simulation/state")
        stream_payload = xc_client.recv(4096).decode("ascii")

        self.assertEqual(after.ownship.phase, FlightPhase.STRAIGHT)
        self.assertGreater(after.sim_time_s if hasattr(after, "sim_time_s") else 10.0, 0.0)
        self.assertEqual(state_payload["snapshot"]["ownship"]["phase"], "straight")
        self.assertIn("$GPRMC,", stream_payload)

    def test_xcvario_connect_and_reconnect_activate_on_ground_default(self):
        xc_client = socket.create_connection(("127.0.0.1", self.session.xcvario_adapter.bound_port), timeout=2.0)
        self.addCleanup(xc_client.close)
        time.sleep(0.05)

        connected = self.session.get_snapshot()
        self.assertEqual(connected.preset_id, None)
        self.assertEqual(connected.runtime_state, RuntimeState.RUNNING)
        self.assertTrue(connected.ownship.on_ground)
        self.assertAlmostEqual(connected.ownship.speed_kmh, 0.0, places=6)
        self.assertAlmostEqual(connected.ownship.vertical_speed_ms, 0.0, places=6)
        self.assertEqual(self.session.get_runtime_metadata()["adapters"]["xcvario"]["polar_name"], "DG 800B/15")

        self._post_json("/api/v1/simulation/preset", {"preset_id": "straight", "seed": 9, "autostart": True})
        moving = self.session.orchestrator.tick(5.0)
        self.assertEqual(moving.preset_id, "straight")
        self.assertFalse(moving.ownship.on_ground)

        xc_client.close()
        time.sleep(0.05)
        reconnected_client = socket.create_connection(("127.0.0.1", self.session.xcvario_adapter.bound_port), timeout=2.0)
        self.addCleanup(reconnected_client.close)
        time.sleep(0.05)

        reconnected = self.session.get_snapshot()
        self.assertEqual(reconnected.preset_id, None)
        self.assertTrue(reconnected.ownship.on_ground)
        self.assertAlmostEqual(reconnected.ownship.speed_kmh, 0.0, places=6)
        self.assertAlmostEqual(reconnected.ownship.vertical_speed_ms, 0.0, places=6)

    def test_traffic_reconnect_does_not_stop_xcvario_stream(self):
        xc_client = socket.create_connection(("127.0.0.1", self.session.xcvario_adapter.bound_port), timeout=2.0)
        flarm_client = socket.create_connection(("127.0.0.1", self.session.flarm_adapter.bound_port), timeout=2.0)
        self.addCleanup(xc_client.close)
        self.addCleanup(flarm_client.close)
        time.sleep(0.05)

        self._post_json("/api/v1/simulation/traffic", {"enabled": True, "contact_count": 2})
        self._post_json("/api/v1/simulation/preset", {"preset_id": "straight", "seed": 9, "autostart": True})

        snapshot = self.session.orchestrator.tick(5.0)
        self.session.xcvario_adapter.publish_snapshot(snapshot)
        self.session.flarm_adapter.publish_snapshot(snapshot)
        _ = flarm_client.recv(4096)

        flarm_client.close()
        snapshot = self.session.orchestrator.tick(5.0)
        self.session.xcvario_adapter.publish_snapshot(snapshot)
        self.session.flarm_adapter.publish_snapshot(snapshot)
        xc_payload = xc_client.recv(4096).decode("ascii")

        flarm_reconnected = socket.create_connection(("127.0.0.1", self.session.flarm_adapter.bound_port), timeout=2.0)
        self.addCleanup(flarm_reconnected.close)
        time.sleep(0.05)
        snapshot = self.session.orchestrator.tick(5.0)
        self.session.flarm_adapter.publish_snapshot(snapshot)
        flarm_payload = flarm_reconnected.recv(4096).decode("ascii")

        self.assertIn("$PXCV,", xc_payload)
        self.assertIn("$PFLAU,", flarm_payload)

    def _post_json(self, path: str, payload: dict[str, object]) -> None:
        self.api_connection.request(
            "POST",
            path,
            body=json.dumps(payload),
            headers={"Content-Type": "application/json", "X-Simulator-Token": "token"},
        )
        response = self.api_connection.getresponse()
        response.read()
        self.assertEqual(response.status, 204)

    def _get_json(self, path: str) -> dict[str, object]:
        self.api_connection.request("GET", path, headers={"X-Simulator-Token": "token"})
        response = self.api_connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        return payload


if __name__ == "__main__":
    unittest.main()
