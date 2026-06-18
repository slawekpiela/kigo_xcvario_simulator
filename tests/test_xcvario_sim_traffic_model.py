import math
import unittest

from kigo_xcvario_simulator.contracts import OwnshipState
from kigo_xcvario_simulator.state import FlightPhase
from kigo_xcvario_simulator.traffic_database import (
    FLARM_TRAFFIC_AIRCRAFT,
    LAB_TRAFFIC_AIRCRAFT_COUNT,
    traffic_aircraft_for,
)
from kigo_xcvario_simulator.traffic_model import MAX_TRAFFIC_RADIUS_M, TRAFFIC_SPEED_RANGE_MS, TrafficGenerator


def _ownship() -> OwnshipState:
    return OwnshipState(
        timestamp_utc="2026-05-08T12:00:00.000Z",
        latitude_deg=49.83833,
        longitude_deg=19.00202,
        gps_altitude_m=500.0,
        static_pressure_hpa=955.0,
        device_qnh_hpa=1013.25,
        vertical_speed_ms=0.0,
        speed_kmh=90.0,
        track_deg=90.0,
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

    def test_all_contacts_stay_inside_100km_bubble_with_slow_orbit_speed(self):
        generator = TrafficGenerator(seed=33)

        for _ in range(8):
            contacts = generator.step(_ownship(), 5.0, contact_count=len(FLARM_TRAFFIC_AIRCRAFT))

            for index, contact in enumerate(contacts):
                distance_m = math.hypot(contact.relative_north_m, contact.relative_east_m)
                with self.subTest(index=index):
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

    def test_additional_contacts_have_varied_altitudes_and_behaviors(self):
        generator = TrafficGenerator(seed=33)

        contacts = generator.step(_ownship(), 1.0, contact_count=len(FLARM_TRAFFIC_AIRCRAFT))

        self.assertLess(min(contact.relative_altitude_m for contact in contacts), -800.0)
        self.assertGreater(max(contact.relative_altitude_m for contact in contacts), 1000.0)
        self.assertLess(min(contact.climb_ms for contact in contacts), -1.0)
        self.assertGreater(max(contact.climb_ms for contact in contacts), 1.0)

    def test_default_contacts_do_not_rotate_onto_collision_course(self):
        generator = TrafficGenerator(seed=33)

        first = generator.step(_ownship(), 1.0, contact_count=3)
        second = generator.step(_ownship(), 10.0, contact_count=3)

        self.assertEqual(first[0].aircraft_id, "DDA857")
        self.assertEqual(second[1].aircraft_id, "DDA85A")
        self.assertEqual(first[0].alarm_level, 0)
        self.assertEqual(second[1].alarm_level, 0)
        self.assertNotEqual(first[0].track_deg, second[0].track_deg)

    def test_negative_dt_is_rejected(self):
        generator = TrafficGenerator(seed=33)

        with self.assertRaises(ValueError):
            generator.step(_ownship(), -1.0, contact_count=1)


if __name__ == "__main__":
    unittest.main()
