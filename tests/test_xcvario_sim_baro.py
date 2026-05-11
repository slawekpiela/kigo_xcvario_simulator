from datetime import datetime, timezone
import unittest

from kigo_xcvario_simulator.baro import (
    STANDARD_QNH_HPA,
    altitude_m_for_static_pressure,
    qnh_hpa_for_static_pressure,
    simulation_timestamp_utc,
    static_pressure_hpa_for_altitude,
)


class SimulatorBaroTests(unittest.TestCase):
    def test_static_pressure_and_altitude_round_trip(self):
        pressure = static_pressure_hpa_for_altitude(450.0, qnh_hpa=1019.7)
        altitude = altitude_m_for_static_pressure(pressure, qnh_hpa=1019.7)
        self.assertAlmostEqual(altitude, 450.0, places=4)

    def test_qnh_reconstruction_matches_original_value(self):
        pressure = static_pressure_hpa_for_altitude(620.0, qnh_hpa=1007.4)
        qnh = qnh_hpa_for_static_pressure(pressure, 620.0)
        self.assertAlmostEqual(qnh, 1007.4, places=4)

    def test_static_pressure_defaults_to_standard_qnh(self):
        pressure = static_pressure_hpa_for_altitude(0.0)
        self.assertAlmostEqual(pressure, STANDARD_QNH_HPA, places=4)

    def test_simulation_timestamp_returns_utc_iso_string(self):
        timestamp = simulation_timestamp_utc(datetime(2026, 5, 8, 10, 0, 0, tzinfo=timezone.utc), 12.345)
        self.assertEqual(timestamp, "2026-05-08T10:00:12.345Z")


if __name__ == "__main__":
    unittest.main()
