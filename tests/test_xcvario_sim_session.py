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
from kigo_xcvario_simulator.contracts import PresetRequest
from kigo_xcvario_simulator.session import SimulatorRuntimeSession
from kigo_xcvario_simulator.state import RuntimeState


class _FakePublisher:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.published = []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def publish_snapshot(self, snapshot) -> None:
        self.published.append(snapshot)


def _config() -> SimulatorRuntimeConfig:
    return SimulatorRuntimeConfig(
        session_id="xcvario-sim",
        seed=12,
        device_qnh_hpa=1013.25,
        home_position=HomePosition(latitude_deg=49.83833, longitude_deg=19.00202, gps_altitude_m=401.0),
        control_api=ControlApiConfig(token="token"),
        xcvario=XcvarioConfig(port=4353, polar_name="DG 800B/15"),
        flarm=EndpointConfig(port=4354),
        scheduler=SchedulerConfig(tick_hz=10, ownship_hz=2, traffic_hz=1),
    )


class SessionAndSchedulerTests(unittest.TestCase):
    def test_manual_ticks_publish_on_expected_cadence(self):
        ownship = _FakePublisher()
        traffic = _FakePublisher()
        session = SimulatorRuntimeSession(_config(), xcvario_adapter=ownship, flarm_adapter=traffic)
        session.load_preset(PresetRequest("straight", seed=9, autostart=True))
        session.set_traffic_config(True, 2)

        for _ in range(10):
            session.scheduler.run_tick()

        self.assertEqual(len(ownship.published), 2)
        self.assertEqual(len(traffic.published), 1)
        self.assertEqual(session.scheduler.tick_count, 10)

    def test_headless_session_starts_and_stops_without_hanging_threads(self):
        ownship = _FakePublisher()
        traffic = _FakePublisher()
        session = SimulatorRuntimeSession(_config(), xcvario_adapter=ownship, flarm_adapter=traffic)
        session.load_preset(PresetRequest("straight", seed=9, autostart=True))

        session.start()
        time.sleep(0.15)
        session.stop()

        self.assertTrue(ownship.started)
        self.assertTrue(traffic.started)
        self.assertTrue(ownship.stopped)
        self.assertTrue(traffic.stopped)
        self.assertFalse(session.started)

    def test_client_connect_default_activates_manual_on_ground_at_home(self):
        ownship = _FakePublisher()
        traffic = _FakePublisher()
        session = SimulatorRuntimeSession(_config(), xcvario_adapter=ownship, flarm_adapter=traffic)
        session.load_preset(PresetRequest("straight", seed=9, autostart=True))
        session.orchestrator.tick(10.0)

        snapshot = session.activate_on_ground_default()

        self.assertEqual(snapshot.preset_id, None)
        self.assertEqual(snapshot.runtime_state, RuntimeState.RUNNING)
        self.assertTrue(snapshot.ownship.on_ground)
        self.assertAlmostEqual(snapshot.ownship.speed_kmh, 0.0, places=6)
        self.assertAlmostEqual(snapshot.ownship.latitude_deg, _config().home_position.latitude_deg, places=6)
        self.assertAlmostEqual(snapshot.ownship.longitude_deg, _config().home_position.longitude_deg, places=6)


if __name__ == "__main__":
    unittest.main()
