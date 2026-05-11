import unittest

from kigo_xcvario_simulator.config import parse_runtime_config
from kigo_xcvario_simulator.xcvario_polar import get_xcvario_polar


class XcvarioConfigTests(unittest.TestCase):
    def test_runtime_config_requires_explicit_xcvario_polar_name(self):
        with self.assertRaisesRegex(ValueError, "xcvario.polar_name"):
            parse_runtime_config(
                {
                    "session_id": "xcvario-sim",
                    "seed": 1,
                    "device_qnh_hpa": 1013.25,
                    "home_position": {
                        "latitude_deg": 49.83833,
                        "longitude_deg": 19.00202,
                        "gps_altitude_m": 401.0,
                    },
                    "control_api": {"bind_host": "127.0.0.1", "port": 8181, "token": "token"},
                    "xcvario": {"bind_host": "127.0.0.1", "port": 4353},
                    "flarm": {"bind_host": "127.0.0.1", "port": 4354},
                    "scheduler": {"tick_hz": 10, "ownship_hz": 2, "traffic_hz": 1},
                }
            )

    def test_dg800b15_polar_matches_upstream_reference_values(self):
        polar = get_xcvario_polar("DG 800B/15")

        self.assertEqual(polar.index, 1360)
        self.assertAlmostEqual(polar.wingload_kg_m2, 38.76, places=6)
        self.assertAlmostEqual(polar.max_ballast_kg, 100.0, places=6)
        self.assertAlmostEqual(polar.wingarea_m2, 10.68, places=6)
        self.assertAlmostEqual(polar.reference_weight_kg, 413.9568, places=4)
        self.assertAlmostEqual(polar.ballast_overload_factor(0.5), 1.120785550569528, places=12)


if __name__ == "__main__":
    unittest.main()
