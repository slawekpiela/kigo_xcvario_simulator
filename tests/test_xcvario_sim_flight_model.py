from datetime import datetime, timezone
import unittest

from kigo_xcvario_simulator.baro import static_pressure_hpa_for_altitude
from kigo_xcvario_simulator.contracts import FlightDirective
from kigo_xcvario_simulator.flight_model import FlightModel
from kigo_xcvario_simulator.state import FlightPhase


class FlightModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = FlightModel(
            seed=17,
            home_latitude_deg=49.83833,
            home_longitude_deg=19.00202,
            home_altitude_m=401.0,
            pressure_reference_qnh_hpa=1013.25,
            device_qnh_hpa=1013.25,
            start_utc=datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc),
        )
        self.initial_state = self.model.reset()

    def test_straight_step_moves_forward_with_constant_altitude(self):
        directive = FlightDirective(
            segment_id="straight_leg",
            phase=FlightPhase.STRAIGHT,
            duration_s=10.0,
            target_heading_deg=90.0,
            target_speed_kmh=90.0,
        )

        next_state = self.model.step(self.initial_state, directive, 10.0)

        self.assertAlmostEqual(next_state.gps_altitude_m, 401.0, places=4)
        self.assertAlmostEqual(next_state.vertical_speed_ms, 0.0, places=4)
        self.assertGreater(next_state.longitude_deg, self.initial_state.longitude_deg)
        self.assertFalse(next_state.on_ground)
        self.assertEqual(next_state.phase, FlightPhase.STRAIGHT)

    def test_straight_uses_configured_altitude_for_gps_and_baro_output(self):
        directive = FlightDirective(
            segment_id="straight_leg",
            phase=FlightPhase.STRAIGHT,
            duration_s=10.0,
            target_heading_deg=90.0,
            target_speed_kmh=90.0,
            baro_altitude_m=850.0,
        )

        next_state = self.model.step(self.initial_state, directive, 1.0)

        self.assertAlmostEqual(next_state.gps_altitude_m, 850.0, places=4)
        self.assertAlmostEqual(next_state.vertical_speed_ms, 0.0, places=4)
        self.assertAlmostEqual(
            next_state.static_pressure_hpa,
            static_pressure_hpa_for_altitude(850.0, qnh_hpa=1013.25),
            places=6,
        )

    def test_baro_altitude_is_ignored_outside_straight_mode(self):
        directive = FlightDirective(
            segment_id="circling_core",
            phase=FlightPhase.CIRCLING_LEFT,
            duration_s=60.0,
            target_heading_deg=180.0,
            target_speed_kmh=78.0,
            baro_altitude_m=850.0,
            turn_radius_m=110.0,
            climb_min_ms=0.0,
            climb_max_ms=0.0,
        )

        next_state = self.model.step(self.initial_state, directive, 1.0)

        self.assertAlmostEqual(next_state.gps_altitude_m, 401.0, places=4)
        self.assertAlmostEqual(
            next_state.static_pressure_hpa,
            static_pressure_hpa_for_altitude(401.0, qnh_hpa=1013.25),
            places=6,
        )

    def test_circling_step_changes_track_and_uses_deterministic_climb(self):
        directive = FlightDirective(
            segment_id="circling_core",
            phase=FlightPhase.CIRCLING_LEFT,
            duration_s=60.0,
            target_heading_deg=180.0,
            target_speed_kmh=78.0,
            turn_radius_m=110.0,
            climb_min_ms=2.0,
            climb_max_ms=3.0,
        )

        first = self.model.step(self.initial_state, directive, 1.0)
        second_model = FlightModel(
            seed=17,
            home_latitude_deg=49.83833,
            home_longitude_deg=19.00202,
            home_altitude_m=401.0,
            pressure_reference_qnh_hpa=1013.25,
            device_qnh_hpa=1013.25,
            start_utc=datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc),
        )
        second_initial = second_model.reset()
        second = second_model.step(second_initial, directive, 1.0)

        self.assertNotEqual(first.track_deg, self.initial_state.track_deg)
        self.assertGreater(first.gps_altitude_m, self.initial_state.gps_altitude_m)
        self.assertAlmostEqual(first.vertical_speed_ms, second.vertical_speed_ms, places=8)
        self.assertEqual(first.phase, FlightPhase.CIRCLING_LEFT)

    def test_circling_variation_changes_smoothly_between_ticks(self):
        directive = FlightDirective(
            segment_id="circling_core",
            phase=FlightPhase.CIRCLING_LEFT,
            duration_s=60.0,
            target_heading_deg=180.0,
            target_speed_kmh=78.0,
            turn_radius_m=110.0,
            climb_min_ms=-1.0,
            climb_max_ms=3.0,
        )

        state = self.initial_state
        samples = []
        for _ in range(30):
            state = self.model.step(state, directive, 0.1)
            samples.append(state.vertical_speed_ms)

        deltas = [abs(right - left) for left, right in zip(samples, samples[1:])]

        self.assertLess(max(deltas), 0.35)
        self.assertGreaterEqual(min(samples), -1.0)
        self.assertLessEqual(max(samples), 3.0)

    def test_circling_climb_range_accepts_reversed_limits(self):
        directive = FlightDirective(
            segment_id="circling_core",
            phase=FlightPhase.CIRCLING_LEFT,
            duration_s=60.0,
            target_heading_deg=180.0,
            target_speed_kmh=78.0,
            turn_radius_m=110.0,
            climb_min_ms=3.0,
            climb_max_ms=2.0,
        )

        state = self.initial_state
        samples = []
        for _ in range(30):
            state = self.model.step(state, directive, 0.1)
            samples.append(state.vertical_speed_ms)

        self.assertGreaterEqual(min(samples), 2.0)
        self.assertLessEqual(max(samples), 3.0)

    def test_circling_speed_varies_smoothly_between_configured_limits(self):
        directive = FlightDirective(
            segment_id="circling_core",
            phase=FlightPhase.CIRCLING_LEFT,
            duration_s=60.0,
            target_heading_deg=180.0,
            target_speed_kmh=78.0,
            speed_min_kmh=76.0,
            speed_max_kmh=80.0,
            turn_radius_m=110.0,
            climb_min_ms=2.0,
            climb_max_ms=2.0,
        )

        state = self.initial_state
        samples = []
        for _ in range(100):
            state = self.model.step(state, directive, 0.1)
            samples.append(state.speed_kmh)

        deltas = [abs(right - left) for left, right in zip(samples, samples[1:])]

        self.assertAlmostEqual(samples[0], 76.0, places=6)
        self.assertAlmostEqual(samples[48], 80.0, places=6)
        self.assertAlmostEqual(samples[96], 76.0, places=6)
        self.assertLess(max(deltas), 0.15)
        self.assertGreaterEqual(min(samples), 76.0)
        self.assertLessEqual(max(samples), 80.0)

    def test_landing_rollout_clamps_to_home_altitude_and_stays_on_ground(self):
        rollout = FlightDirective(
            segment_id="rollout",
            phase=FlightPhase.GLIDER_LANDING,
            duration_s=12.0,
            target_heading_deg=90.0,
            target_speed_kmh=24.0,
            sink_ms=0.0,
            on_ground=True,
        )
        airborne = FlightDirective(
            segment_id="approach",
            phase=FlightPhase.GLIDER_LANDING,
            duration_s=30.0,
            target_heading_deg=90.0,
            target_speed_kmh=78.0,
            sink_ms=-1.8,
        )

        landing_state = self.model.step(self.initial_state, airborne, 5.0)
        rollout_state = self.model.step(landing_state, rollout, 5.0)

        self.assertTrue(rollout_state.on_ground)
        self.assertAlmostEqual(rollout_state.gps_altitude_m, 401.0, places=4)
        self.assertAlmostEqual(rollout_state.vertical_speed_ms, 0.0, places=4)
        self.assertGreater(rollout_state.longitude_deg, landing_state.longitude_deg)

    def test_device_qnh_change_does_not_change_static_pressure_for_same_altitude(self):
        directive = FlightDirective(
            segment_id="straight_leg",
            phase=FlightPhase.STRAIGHT,
            duration_s=10.0,
            target_heading_deg=90.0,
            target_speed_kmh=90.0,
        )

        before = self.model.step(self.initial_state, directive, 1.0)
        self.model.set_device_qnh_hpa(999.4)
        after = self.model.step(before, directive, 1.0)

        self.assertAlmostEqual(after.gps_altitude_m, before.gps_altitude_m, places=4)
        self.assertAlmostEqual(after.static_pressure_hpa, before.static_pressure_hpa, places=6)
        self.assertAlmostEqual(after.device_qnh_hpa, 999.4, places=4)


if __name__ == "__main__":
    unittest.main()
