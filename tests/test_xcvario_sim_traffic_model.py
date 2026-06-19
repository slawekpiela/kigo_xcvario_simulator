import math
import unittest

from kigo_xcvario_simulator.contracts import TRAFFIC_CIRCLING_RADIUS_MAX_M, TRAFFIC_MOTION_STRAIGHT, OwnshipState
from kigo_xcvario_simulator.state import FlightPhase
from kigo_xcvario_simulator.traffic_database import (
    FLARM_TRAFFIC_AIRCRAFT,
    LAB_TRAFFIC_AIRCRAFT_COUNT,
    traffic_aircraft_for,
)
from kigo_xcvario_simulator.traffic_model import (
    MAX_TRAFFIC_RADIUS_M,
    METERS_PER_DEGREE_LATITUDE,
    MIN_CIRCLING_RADIUS_M,
    MIN_TRAFFIC_RADIUS_M,
    ORBIT_GAIN_RANGE_M,
    ORBIT_STRAIGHT_DURATION_S,
    TRAFFIC_CLIMB_RANGE_MS,
    TRAFFIC_SPEED_RANGE_MS,
    TrafficGenerator,
)


def _ownship(
    *,
    latitude_delta_deg: float = 0.0,
    longitude_delta_deg: float = 0.0,
    altitude_delta_m: float = 0.0,
    track_deg: float = 90.0,
) -> OwnshipState:
    return OwnshipState(
        timestamp_utc="2026-05-08T12:00:00.000Z",
        latitude_deg=49.83833 + latitude_delta_deg,
        longitude_deg=19.00202 + longitude_delta_deg,
        gps_altitude_m=500.0 + altitude_delta_m,
        static_pressure_hpa=955.0,
        device_qnh_hpa=1013.25,
        vertical_speed_ms=0.0,
        speed_kmh=90.0,
        track_deg=track_deg,
        on_ground=False,
        phase=FlightPhase.STRAIGHT,
    )


class TrafficGeneratorTests(unittest.TestCase):
    def test_zero_contacts_returns_empty_tuple(self):
        generator = TrafficGenerator(seed=11)

        contacts = generator.step(_ownship(), 1.0, contact_count=0)

        self.assertEqual(contacts, ())

    def test_same_seed_and_inputs_are_deterministic(self):
        generator_a = TrafficGenerator(seed=22)
        generator_b = TrafficGenerator(seed=22)

        contacts_a = generator_a.step(_ownship(), 1.0, contact_count=3)
        contacts_b = generator_b.step(_ownship(), 1.0, contact_count=3)

        self.assertEqual(contacts_a, contacts_b)

    def test_contacts_move_over_time(self):
        generator = TrafficGenerator(seed=33)

        first = generator.step(_ownship(), 1.0, contact_count=2)
        second = generator.step(_ownship(), 1.0, contact_count=2)

        self.assertNotEqual(first[0].relative_north_m, second[0].relative_north_m)
        self.assertNotEqual(first[0].relative_east_m, second[0].relative_east_m)

    def test_collision_course_moves_primary_contact_towards_ownship(self):
        generator = TrafficGenerator(seed=33)

        first = generator.step(_ownship(), 1.0, contact_count=2, collision_course=True)
        second = generator.step(_ownship(), 1.0, contact_count=2, collision_course=True)

        first_distance = abs(first[0].relative_east_m) + abs(first[0].relative_north_m)
        second_distance = abs(second[0].relative_east_m) + abs(second[0].relative_north_m)

        self.assertLess(second_distance, first_distance)
        self.assertEqual(first[0].track_deg, 270.0)
        self.assertTrue(first[0].aircraft_id)

    def test_contacts_use_configured_flarm_aircraft_metadata(self):
        generator = TrafficGenerator(seed=33)

        contacts = generator.step(_ownship(), 1.0, contact_count=3)
        expected = traffic_aircraft_for(33, 0)

        self.assertEqual(contacts[0].aircraft_id, expected.device_id)
        self.assertEqual(contacts[0].competition_id, expected.competition_id)
        self.assertEqual(contacts[0].registration, expected.registration)
        self.assertEqual(contacts[0].aircraft_model, expected.aircraft_model)

    def test_configured_flarm_aircraft_are_requested_lab_ids(self):
        self.assertEqual(
            [aircraft.device_id for aircraft in FLARM_TRAFFIC_AIRCRAFT[:LAB_TRAFFIC_AIRCRAFT_COUNT]],
            ["DDA857", "DDA85A", "DDA85C", "DDA86A", "DDA88F", "DDA896"],
        )
        self.assertEqual(FLARM_TRAFFIC_AIRCRAFT[0].registration, "D-6676")
        self.assertEqual(FLARM_TRAFFIC_AIRCRAFT[1].competition_id, "L1")
        self.assertEqual(FLARM_TRAFFIC_AIRCRAFT[2].aircraft_model, "Hornet")
        self.assertEqual(FLARM_TRAFFIC_AIRCRAFT[3].competition_id, "1A")
        self.assertEqual(FLARM_TRAFFIC_AIRCRAFT[4].registration, "DKERO")
        self.assertEqual(FLARM_TRAFFIC_AIRCRAFT[4].competition_id, "")
        self.assertEqual(FLARM_TRAFFIC_AIRCRAFT[5].registration, "D-5799")
        self.assertEqual(len(FLARM_TRAFFIC_AIRCRAFT), 29)
        self.assertEqual(len({aircraft.device_id for aircraft in FLARM_TRAFFIC_AIRCRAFT}), len(FLARM_TRAFFIC_AIRCRAFT))
        for aircraft in FLARM_TRAFFIC_AIRCRAFT:
            with self.subTest(device_id=aircraft.device_id):
                self.assertRegex(aircraft.device_id, r"^[0-9A-F]{6}$")
                if aircraft.competition_id:
                    self.assertRegex(aircraft.competition_id, r"^[A-Z0-9]{1,4}$")
                self.assertTrue(aircraft.registration)
                self.assertTrue(aircraft.aircraft_model)

    def test_all_contacts_stay_between_5km_and_30km_with_slow_orbit_speed(self):
        generator = TrafficGenerator(seed=33)

        for _ in range(8):
            contacts = generator.step(_ownship(), 5.0, contact_count=len(FLARM_TRAFFIC_AIRCRAFT))

            for index, contact in enumerate(contacts):
                distance_m = math.hypot(contact.relative_north_m, contact.relative_east_m)
                with self.subTest(index=index):
                    self.assertGreaterEqual(distance_m, MIN_TRAFFIC_RADIUS_M)
                    self.assertLessEqual(distance_m, MAX_TRAFFIC_RADIUS_M)
                    self.assertGreaterEqual(contact.speed_ms, TRAFFIC_SPEED_RANGE_MS[0])
                    self.assertLessEqual(contact.speed_ms, TRAFFIC_SPEED_RANGE_MS[1])

    def test_all_default_contacts_orbit_periodically(self):
        generator = TrafficGenerator(seed=33)

        first = generator.step(_ownship(), 1.0, contact_count=len(FLARM_TRAFFIC_AIRCRAFT))
        second = generator.step(_ownship(), 180.0, contact_count=len(FLARM_TRAFFIC_AIRCRAFT))

        for index in range(len(FLARM_TRAFFIC_AIRCRAFT)):
            with self.subTest(index=index):
                self.assertNotAlmostEqual(first[index].relative_north_m, second[index].relative_north_m, delta=0.1)
                self.assertNotAlmostEqual(first[index].relative_east_m, second[index].relative_east_m, delta=0.1)

    def test_orbit_contacts_use_random_radius_range_for_all_contacts(self):
        generator = TrafficGenerator(seed=33)

        generator.step(
            _ownship(),
            1.0,
            contact_count=len(FLARM_TRAFFIC_AIRCRAFT),
            circling_radius_min_m=300.0,
            circling_radius_max_m=500.0,
        )

        radii_m = []
        for index, state in generator._orbit_states.items():
            radii_m.append(state.semi_major_m)
            with self.subTest(index=index):
                self.assertGreaterEqual(state.semi_major_m, 300.0)
                self.assertLessEqual(state.semi_major_m, 500.0)
                self.assertGreaterEqual(state.semi_minor_m, state.semi_major_m * 0.91)
                self.assertLess(state.semi_minor_m, state.semi_major_m)
        self.assertGreater(max(radii_m) - min(radii_m), 100.0)

    def test_straight_motion_mode_keeps_contacts_in_range_and_moving(self):
        generator = TrafficGenerator(seed=33)

        first = generator.step(
            _ownship(),
            1.0,
            contact_count=len(FLARM_TRAFFIC_AIRCRAFT),
            motion_mode=TRAFFIC_MOTION_STRAIGHT,
        )
        second = generator.step(
            _ownship(),
            10.0,
            contact_count=len(FLARM_TRAFFIC_AIRCRAFT),
            motion_mode=TRAFFIC_MOTION_STRAIGHT,
        )

        for index, contact in enumerate(first):
            distance_m = math.hypot(contact.relative_north_m, contact.relative_east_m)
            with self.subTest(index=index):
                self.assertGreaterEqual(distance_m, MIN_TRAFFIC_RADIUS_M)
                self.assertLessEqual(distance_m, MAX_TRAFFIC_RADIUS_M)
                self.assertGreaterEqual(contact.speed_ms, TRAFFIC_SPEED_RANGE_MS[0])
                self.assertLessEqual(contact.speed_ms, TRAFFIC_SPEED_RANGE_MS[1])
                movement_m = math.hypot(
                    second[index].relative_north_m - contact.relative_north_m,
                    second[index].relative_east_m - contact.relative_east_m,
                )
                self.assertGreater(movement_m, 0.1)

    def test_additional_contacts_have_varied_altitudes_and_behaviors(self):
        generator = TrafficGenerator(seed=33)

        contacts = generator.step(_ownship(), 1.0, contact_count=len(FLARM_TRAFFIC_AIRCRAFT))

        self.assertLess(min(contact.relative_altitude_m for contact in contacts), -800.0)
        self.assertGreater(max(contact.relative_altitude_m for contact in contacts), 1000.0)
        self.assertGreater(max(contact.climb_ms for contact in contacts), 3.0)

    def test_all_default_contacts_orbit_with_requested_climb_range(self):
        generator = TrafficGenerator(seed=33)

        first = generator.step(_ownship(), 1.0, contact_count=len(FLARM_TRAFFIC_AIRCRAFT))
        second = generator.step(_ownship(), 120.0, contact_count=len(FLARM_TRAFFIC_AIRCRAFT))

        minimum_period_s = math.pi * 2.0 * MIN_CIRCLING_RADIUS_M / TRAFFIC_SPEED_RANGE_MS[1]
        self.assertGreaterEqual(minimum_period_s, 120.0)
        for index in range(len(FLARM_TRAFFIC_AIRCRAFT)):
            with self.subTest(index=index):
                self.assertGreaterEqual(first[index].climb_ms, TRAFFIC_CLIMB_RANGE_MS[0])
                self.assertLessEqual(first[index].climb_ms, TRAFFIC_CLIMB_RANGE_MS[1])
                if second[index].climb_ms > 0.0:
                    self.assertGreaterEqual(second[index].climb_ms, TRAFFIC_CLIMB_RANGE_MS[0])
                    self.assertLessEqual(second[index].climb_ms, TRAFFIC_CLIMB_RANGE_MS[1])
                self.assertNotAlmostEqual(first[index].relative_north_m, second[index].relative_north_m, delta=0.1)
                self.assertNotAlmostEqual(first[index].relative_east_m, second[index].relative_east_m, delta=0.1)

    def test_orbit_mode_alternates_climb_and_two_minute_straight_leg(self):
        generator = TrafficGenerator(seed=33)

        generator.step(_ownship(), 1.0, contact_count=1)
        state = generator._orbit_states[0]
        self.assertEqual(state.phase, "orbit")
        self.assertGreaterEqual(state.climb_target_m, ORBIT_GAIN_RANGE_M[0])
        self.assertLessEqual(state.climb_target_m, ORBIT_GAIN_RANGE_M[1])

        time_to_straight_s = (state.climb_target_m - state.climb_gained_m) / state.climb_ms
        generator.step(_ownship(), time_to_straight_s + 1.0, contact_count=1)
        state = generator._orbit_states[0]
        self.assertEqual(state.phase, "straight")
        self.assertAlmostEqual(state.phase_elapsed_s, 1.0, places=5)

        generator.step(_ownship(), ORBIT_STRAIGHT_DURATION_S - 1.5, contact_count=1)
        state = generator._orbit_states[0]
        self.assertEqual(state.phase, "straight")

        generator.step(_ownship(), 0.5, contact_count=1)
        state = generator._orbit_states[0]
        self.assertEqual(state.phase, "orbit")
        self.assertEqual(state.cycle_index, 1)
        self.assertEqual(state.climb_gained_m, 0.0)

    def test_orbit_mode_keeps_stationary_traffic_in_range_over_cycles(self):
        generator = TrafficGenerator(seed=33)

        for _ in range(300):
            contacts = generator.step(_ownship(), 10.0, contact_count=len(FLARM_TRAFFIC_AIRCRAFT))

            for index, contact in enumerate(contacts):
                distance_m = math.hypot(contact.relative_north_m, contact.relative_east_m)
                with self.subTest(index=index):
                    self.assertGreaterEqual(distance_m, MIN_TRAFFIC_RADIUS_M)
                    self.assertLessEqual(distance_m, MAX_TRAFFIC_RADIUS_M)

    def test_traffic_start_anchor_does_not_follow_moving_ownship(self):
        generator = TrafficGenerator(seed=33)

        first = generator.step(_ownship(), 1.0, contact_count=1)
        moved = generator.step(_ownship(latitude_delta_deg=0.01), 0.0, contact_count=1)

        self.assertAlmostEqual(
            moved[0].relative_north_m,
            first[0].relative_north_m - 0.01 * METERS_PER_DEGREE_LATITUDE,
            delta=0.1,
        )
        self.assertAlmostEqual(moved[0].relative_east_m, first[0].relative_east_m, delta=0.1)

    def test_default_contacts_do_not_rotate_onto_collision_course(self):
        generator = TrafficGenerator(seed=33)

        first = generator.step(_ownship(), 1.0, contact_count=3)
        second = generator.step(_ownship(), 10.0, contact_count=3)

        self.assertEqual(first[0].aircraft_id, "DDA857")
        self.assertEqual(second[1].aircraft_id, "DDA85A")
        self.assertEqual(first[0].alarm_level, 0)
        self.assertEqual(second[1].alarm_level, 0)
        self.assertNotEqual(first[0].track_deg, second[0].track_deg)

    def test_low_circling_radius_is_clamped_to_preserve_minimum_period(self):
        generator = TrafficGenerator(seed=33)

        generator.step(
            _ownship(),
            1.0,
            contact_count=3,
            circling_radius_min_m=1.0,
            circling_radius_max_m=1.0,
        )

        for index, state in generator._orbit_states.items():
            with self.subTest(index=index):
                self.assertAlmostEqual(state.semi_major_m, MIN_CIRCLING_RADIUS_M, places=6)
                self.assertLessEqual(state.semi_major_m, TRAFFIC_CIRCLING_RADIUS_MAX_M)

    def test_negative_dt_is_rejected(self):
        generator = TrafficGenerator(seed=33)

        with self.assertRaises(ValueError):
            generator.step(_ownship(), -1.0, contact_count=1)


if __name__ == "__main__":
    unittest.main()
