from pathlib import Path
import unittest

from kigo_xcvario_simulator.config import load_runtime_config
from kigo_xcvario_simulator.replay import parse_igc
from kigo_xcvario_simulator.session import SimulatorRuntimeSession
from kigo_xcvario_simulator.state import RuntimeState


CONFIG = Path(__file__).resolve().parents[1] / "kigo_xcvario_simulator/examples/runtime.example.json"


def igc(*records):
    return ("\n".join(records) + "\n").encode("ascii")


class ReplayTests(unittest.TestCase):
    def test_igc_interpolation_and_midnight(self):
        track = parse_igc(igc(
            "B2359585100000N01900000EA0100001000",
            "B2359595100600N01900000EA0101001010",
            "B0000005101200N01900000EA0102001020",
        ))
        self.assertEqual(track.duration_s, 2)
        middle = track.sample(0.5)
        self.assertAlmostEqual(middle.latitude_deg, 51.005, places=4)
        self.assertAlmostEqual(middle.altitude_m, 1005)
        self.assertAlmostEqual(middle.climb_ms, 10)
        self.assertAlmostEqual(middle.track_deg, 0)
        self.assertGreater(middle.speed_kmh, 1000)

    def test_invalid_fixes_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            parse_igc(igc("B1200005100000N01900000EV0100001000"))
        with self.assertRaisesRegex(ValueError, "out of order"):
            parse_igc(igc("B1200105100000N01900000EA0100001000",
                          "B1200005100000N01900000EA0100001000"))

    def test_replay_pause_resume_manual_and_traffic(self):
        session = SimulatorRuntimeSession(load_runtime_config(CONFIG), activate_on_connect=False)
        session.set_traffic_config(True, 3)
        session.load_replay_igc(igc("B1200005100000N01900000EA0100001000",
                                    "B1200025100120N01900000EA0102001020"))
        before = session.get_snapshot()
        self.assertEqual(before.runtime_state, RuntimeState.RUNNING)
        self.assertEqual(session.get_replay_status()["duration_s"], 2)
        self.assertTrue(session.orchestrator.get_traffic_config().enabled)
        self.assertEqual(session.orchestrator.get_traffic_config().contact_count, 3)
        session.orchestrator.tick(1)
        halfway = session.get_snapshot()
        self.assertAlmostEqual(halfway.ownship.latitude_deg, 51.001)
        self.assertEqual(len(halfway.traffic), 3)
        session.pause_simulation()
        session.orchestrator.tick(1)
        self.assertEqual(session.get_snapshot().sim_time_s, 1)
        session.start_simulation()
        session.orchestrator.tick(1)
        self.assertEqual(session.get_snapshot().runtime_state, RuntimeState.PAUSED)
        self.assertAlmostEqual(session.get_snapshot().ownship.latitude_deg, 51.002)
        session.reset_simulation()
        self.assertEqual(session.get_snapshot().sim_time_s, 0)


if __name__ == "__main__":
    unittest.main()
