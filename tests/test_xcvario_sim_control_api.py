import http.client
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kigo_xcvario_simulator.airport_lookup import AirportLookup
from kigo_xcvario_simulator.baro import qnh_hpa_for_static_pressure, static_pressure_hpa_for_altitude
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
from kigo_xcvario_simulator.traffic_database import FLARM_TRAFFIC_AIRCRAFT


class _FakePublisher:
    def __init__(self) -> None:
        self.oat_c = 18.0
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True
        return None

    def stop(self) -> None:
        self.stopped = True
        return None

    def publish_snapshot(self, _snapshot) -> None:
        return None

    def set_oat_c(self, oat_c: float) -> None:
        self.oat_c = float(oat_c)


class _FakeBridgeControl:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def status(self, payload: dict[str, object]) -> dict[str, object]:
        return self._record("status", payload)

    def start(self, payload: dict[str, object]) -> dict[str, object]:
        return self._record("start", payload)

    def stop(self, payload: dict[str, object]) -> dict[str, object]:
        return self._record("stop", payload)

    def restart(self, payload: dict[str, object]) -> dict[str, object]:
        return self._record("restart", payload)

    def _record(self, action: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append((action, payload))
        return {
            "action": action,
            "nodes": [
                {
                    "id": "pi",
                    "ssh_target": "admin@192.168.0.114",
                    "simulator_host": "192.168.0.105",
                    "primary_active": action in {"start", "restart", "status"},
                    "flarm_active": action in {"start", "restart", "status"},
                }
            ],
        }


def _config() -> SimulatorRuntimeConfig:
    return SimulatorRuntimeConfig(
        session_id="xcvario-sim",
        seed=15,
        device_qnh_hpa=1013.25,
        home_position=HomePosition(latitude_deg=49.83833, longitude_deg=19.00202, gps_altitude_m=401.0),
        control_api=ControlApiConfig(bind_host="127.0.0.1", port=0),
        xcvario=XcvarioConfig(port=4353, polar_name="DG 800B/15"),
        flarm=EndpointConfig(port=4354),
        scheduler=SchedulerConfig(tick_hz=10, ownship_hz=2, traffic_hz=1),
    )


class ControlApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = SimulatorRuntimeSession(
            _config(),
            xcvario_adapter=_FakePublisher(),
            sxhawk_adapter=_FakePublisher(),
            flarm_adapter=_FakePublisher(),
        )
        self.session.start()
        self.bridge_control = _FakeBridgeControl()
        self.api = ControlApiServer(
            bind_host="127.0.0.1",
            port=0,
            session=self.session,
            bridge_control=self.bridge_control,
        )
        self.api.start()
        self.connection = http.client.HTTPConnection("127.0.0.1", self.api.bound_port, timeout=2.0)

    def tearDown(self) -> None:
        self.connection.close()
        self.api.stop()
        self.session.stop()

    def test_state_endpoint_returns_snapshot_without_auth(self):
        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(response.status, 200)
        self.assertIn("snapshot", payload)
        self.assertIn("runtime", payload)

    def test_post_endpoints_drive_runtime_state(self):
        self.connection.request(
            "POST",
            "/api/v1/simulation/preset",
            body=json.dumps({"preset_id": "straight", "seed": 7, "autostart": True}),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()
        self.assertEqual(response.status, 204)

        self.connection.request(
            "POST",
            "/api/v1/simulation/traffic",
            body=json.dumps({"enabled": True, "contact_count": 2, "collision_course": True}),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()
        self.assertEqual(response.status, 204)

        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["snapshot"]["preset_id"], "straight")
        self.assertEqual(payload["runtime"]["traffic_config"]["contact_count"], 2)
        self.assertEqual(payload["runtime"]["traffic_config"]["collision_course"], True)

    def test_traffic_endpoint_defaults_to_all_contacts_when_count_is_missing(self):
        self.connection.request(
            "POST",
            "/api/v1/simulation/traffic",
            body=json.dumps({"enabled": True}),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()
        self.assertEqual(response.status, 204)

        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["runtime"]["traffic_config"]["contact_count"], len(FLARM_TRAFFIC_AIRCRAFT))

    def test_wind_endpoint_updates_snapshot_and_runtime_metadata(self):
        self.connection.request(
            "POST",
            "/api/v1/simulation/wind",
            body=json.dumps({"direction_deg": 450.0, "speed_kmh": 25.5}),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()
        self.assertEqual(response.status, 204)

        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["snapshot"]["wind"]["direction_deg"], 90.0)
        self.assertEqual(payload["snapshot"]["wind"]["speed_kmh"], 25.5)
        self.assertEqual(payload["runtime"]["wind"]["direction_deg"], 90.0)
        self.assertEqual(payload["runtime"]["wind"]["speed_kmh"], 25.5)

    def test_oat_endpoint_updates_runtime_metadata_and_xcvario_adapter(self):
        self.connection.request(
            "POST",
            "/api/v1/simulation/oat",
            body=json.dumps({"oat_c": 7.5}),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()
        self.assertEqual(response.status, 204)

        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["runtime"]["environment"]["oat_c"], 7.5)
        self.assertEqual(self.session.xcvario_adapter.oat_c, 7.5)

    def test_altimeter_endpoint_updates_device_qnh_and_altitude(self):
        self.connection.request(
            "POST",
            "/api/v1/simulation/altimeter",
            body=json.dumps({"qnh_hpa": 995.5}),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()
        self.assertEqual(response.status, 204)

        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertAlmostEqual(payload["snapshot"]["ownship"]["device_qnh_hpa"], 995.5, places=6)
        self.assertAlmostEqual(payload["runtime"]["environment"]["device_qnh_hpa"], 995.5, places=6)
        self.assertAlmostEqual(
            payload["runtime"]["environment"]["static_pressure_hpa"],
            payload["snapshot"]["ownship"]["static_pressure_hpa"],
            places=6,
        )

        static_pressure_hpa = payload["snapshot"]["ownship"]["static_pressure_hpa"]
        self.connection.request(
            "POST",
            "/api/v1/simulation/altimeter",
            body=json.dumps({"altitude_m": 875.0}),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()
        self.assertEqual(response.status, 204)

        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertAlmostEqual(payload["snapshot"]["ownship"]["device_altitude_m"], 875.0, places=6)
        self.assertAlmostEqual(payload["runtime"]["environment"]["device_altitude_m"], 875.0, places=6)
        self.assertAlmostEqual(
            payload["snapshot"]["ownship"]["device_qnh_hpa"],
            qnh_hpa_for_static_pressure(static_pressure_hpa, 875.0),
            places=6,
        )

    def test_device_endpoint_switches_primary_adapter(self):
        self.connection.request(
            "POST",
            "/api/v1/simulation/device",
            body=json.dumps({"primary_device": "sxhawk"}),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()
        self.assertEqual(response.status, 204)

        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["runtime"]["primary_device"], "sxhawk")
        self.assertTrue(payload["runtime"]["adapters"]["sxhawk"]["active"])
        self.assertFalse(payload["runtime"]["adapters"]["xcvario"]["active"])
        self.assertTrue(self.session.xcvario_adapter.stopped)
        self.assertTrue(self.session.sxhawk_adapter.started)

    def test_start_airport_endpoint_places_ownship_from_cached_icao_lookup(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "openaip"
            data_dir.mkdir()
            (data_dir / "us_apt.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "MINDEN TAHOE AIRPORT",
                            "icaoCode": "KMEV",
                            "geometry": {"type": "Point", "coordinates": [-119.751, 39.0003]},
                            "elevation": {"value": 1439, "unit": 0},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            cache_path = Path(temp_dir) / "airport-cache.json"
            self.session._airport_lookup = AirportLookup(data_dirs=(data_dir,), cache_path=cache_path)

            self.connection.request(
                "POST",
                "/api/v1/simulation/start-airport",
                body=json.dumps({"icao": "kmev"}),
                headers={"Content-Type": "application/json"},
            )
            response = self.connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))

            self.assertEqual(response.status, 200)
            self.assertEqual(payload["airport"]["icao"], "KMEV")
            self.assertTrue(cache_path.exists())

            self.connection.request("GET", "/api/v1/simulation/state")
            response = self.connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))

            ownship = payload["snapshot"]["ownship"]
            self.assertAlmostEqual(ownship["latitude_deg"], 39.0003, places=6)
            self.assertAlmostEqual(ownship["longitude_deg"], -119.751, places=6)
            self.assertAlmostEqual(ownship["gps_altitude_m"], 1439.0, places=6)
            self.assertTrue(ownship["on_ground"])
            self.assertAlmostEqual(ownship["speed_kmh"], 0.0, places=6)
            self.assertEqual(payload["runtime"]["start_airport"]["icao"], "KMEV")

    def test_start_airport_endpoint_accepts_location_name_alias(self):
        with TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "airport-cache.json"
            self.session._airport_lookup = AirportLookup(
                data_dirs=(Path(temp_dir) / "missing",),
                cache_path=cache_path,
            )

            self.connection.request(
                "POST",
                "/api/v1/simulation/start-airport",
                body=json.dumps({"icao": "Minden Tahoe"}),
                headers={"Content-Type": "application/json"},
            )
            response = self.connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["airport"]["icao"], "KMEV")
        self.assertAlmostEqual(payload["snapshot"]["ownship"]["latitude_deg"], 39.0003, places=6)
        self.assertAlmostEqual(payload["snapshot"]["ownship"]["longitude_deg"], -119.751, places=6)

    def test_preset_endpoint_accepts_on_ground(self):
        self.connection.request(
            "POST",
            "/api/v1/simulation/preset",
            body=json.dumps({"preset_id": "on_ground", "seed": 7, "autostart": True}),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()

        self.assertEqual(response.status, 204)

        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["snapshot"]["preset_id"], "on_ground")
        self.assertTrue(payload["snapshot"]["ownship"]["on_ground"])
        self.assertAlmostEqual(payload["snapshot"]["ownship"]["speed_kmh"], 0.0, places=6)
        self.assertAlmostEqual(payload["snapshot"]["ownship"]["vertical_speed_ms"], 0.0, places=6)

    def test_manual_mode_accepts_on_ground_and_circling_speed_range(self):
        self.connection.request(
            "POST",
            "/api/v1/simulation/manual-mode",
            body=json.dumps({"phase": "on_ground"}),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()

        self.assertEqual(response.status, 204)

        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["snapshot"]["preset_id"], None)
        self.assertTrue(payload["snapshot"]["ownship"]["on_ground"])
        self.assertAlmostEqual(payload["snapshot"]["ownship"]["speed_kmh"], 0.0, places=6)

        self.connection.request(
            "POST",
            "/api/v1/simulation/manual-mode",
            body=json.dumps(
                {
                    "phase": "circling_left",
                    "speed_min_kmh": 90.0,
                    "speed_max_kmh": 110.0,
                    "climb_min_ms": 2.0,
                    "climb_max_ms": 2.0,
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()

        self.assertEqual(response.status, 204)

        self.connection.request(
            "POST",
            "/api/v1/simulation/manual-mode",
            body=json.dumps({"phase": "straight", "speed_kmh": 100.0, "wysokosc": 875.0}),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()

        self.assertEqual(response.status, 204)

        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        immediate_payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(immediate_payload["snapshot"]["ownship"]["phase"], "straight")
        self.assertAlmostEqual(immediate_payload["snapshot"]["ownship"]["speed_kmh"], 100.0, places=6)
        self.assertAlmostEqual(immediate_payload["snapshot"]["ownship"]["gps_altitude_m"], 875.0, places=6)
        self.assertAlmostEqual(immediate_payload["snapshot"]["ownship"]["vertical_speed_ms"], 0.0, places=6)

        self.session.orchestrator.start()
        self.session.orchestrator.tick(1.0)
        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["snapshot"]["ownship"]["phase"], "straight")
        self.assertAlmostEqual(payload["snapshot"]["ownship"]["gps_altitude_m"], 875.0, places=6)
        self.assertAlmostEqual(payload["snapshot"]["ownship"]["vertical_speed_ms"], 0.0, places=6)
        self.assertAlmostEqual(
            payload["snapshot"]["ownship"]["static_pressure_hpa"],
            static_pressure_hpa_for_altitude(875.0, qnh_hpa=1013.25),
            places=6,
        )

    def test_manual_straight_accepts_climb_range(self):
        self.connection.request(
            "POST",
            "/api/v1/simulation/manual-mode",
            body=json.dumps(
                {
                    "phase": "straight",
                    "speed_kmh": 100.0,
                    "wysokosc": 875.0,
                    "climb_min_ms": -1.0,
                    "climb_max_ms": 3.0,
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        response.read()

        self.assertEqual(response.status, 204)

        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        immediate_payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(immediate_payload["snapshot"]["ownship"]["phase"], "straight")
        self.assertAlmostEqual(immediate_payload["snapshot"]["ownship"]["gps_altitude_m"], 875.0, places=6)
        self.assertAlmostEqual(immediate_payload["snapshot"]["ownship"]["vertical_speed_ms"], 0.0, places=6)

        self.session.orchestrator.start()
        self.session.orchestrator.tick(1.0)
        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["snapshot"]["ownship"]["phase"], "straight")
        self.assertAlmostEqual(payload["snapshot"]["ownship"]["gps_altitude_m"], 875.0, places=6)
        self.assertAlmostEqual(payload["snapshot"]["ownship"]["vertical_speed_ms"], 0.0, places=6)
        self.assertAlmostEqual(
            payload["snapshot"]["ownship"]["static_pressure_hpa"],
            static_pressure_hpa_for_altitude(payload["snapshot"]["ownship"]["gps_altitude_m"], qnh_hpa=1013.25),
            places=6,
        )

        self.session.orchestrator.tick(1.0)
        self.connection.request("GET", "/api/v1/simulation/state")
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["snapshot"]["ownship"]["phase"], "straight")
        self.assertAlmostEqual(payload["snapshot"]["ownship"]["gps_altitude_m"], 874.0, places=6)
        self.assertAlmostEqual(payload["snapshot"]["ownship"]["vertical_speed_ms"], -1.0, places=6)
        self.assertAlmostEqual(
            payload["snapshot"]["ownship"]["static_pressure_hpa"],
            static_pressure_hpa_for_altitude(payload["snapshot"]["ownship"]["gps_altitude_m"], qnh_hpa=1013.25),
            places=6,
        )

    def test_bad_preset_returns_json_error(self):
        self.connection.request(
            "POST",
            "/api/v1/simulation/preset",
            body=json.dumps({"preset_id": "missing", "seed": 7, "autostart": True}),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(response.status, 400)
        self.assertEqual(payload["error"], "bad_request")
        self.assertIn("Unknown preset_id", payload["message"])

    def test_bridge_control_endpoint_delegates_to_bridge_controller(self):
        body = {
            "primary_port": 4353,
            "flarm_port": 4354,
            "nodes": [
                {
                    "id": "pi",
                    "ssh_target": "admin@192.168.0.114",
                    "identity_file": "/Users/slawekpiela/.ssh/kigo_pi",
                    "simulator_host": "192.168.0.105",
                    "workdir": "/home/admin/kigo_xcvario_simulator",
                }
            ],
        }
        self.connection.request(
            "POST",
            "/api/v1/bridges/start",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["action"], "start")
        self.assertEqual(payload["nodes"][0]["id"], "pi")
        self.assertEqual(self.bridge_control.calls, [("start", body)])

    def test_sse_endpoint_emits_initial_state_event(self):
        self.connection.request("GET", "/api/v1/events")
        response = self.connection.getresponse()
        lines = [response.fp.readline().decode("utf-8") for _ in range(6)]
        payload = "".join(lines)

        self.assertEqual(response.status, 200)
        self.assertIn("event: state", payload)
        self.assertIn("event: ownship", payload)


if __name__ == "__main__":
    unittest.main()
