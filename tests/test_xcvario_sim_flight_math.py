import unittest

from kigo_xcvario_simulator.flight_math import (
    advance_heading_deg,
    advance_position,
    bearing_between_points_deg,
    calculate_turn_radius_m,
    calculate_turn_rate_deg_s,
    ground_velocity_from_true_wind,
    normalize_heading_deg,
    travel_distance_m,
)


class SimulatorFlightMathTests(unittest.TestCase):
    def test_normalize_heading_wraps_negative_and_large_values(self):
        self.assertAlmostEqual(normalize_heading_deg(-10.0), 350.0)
        self.assertAlmostEqual(normalize_heading_deg(725.0), 5.0)

    def test_travel_distance_uses_kmh_and_seconds(self):
        self.assertAlmostEqual(travel_distance_m(72.0, 10.0), 200.0, places=3)

    def test_ground_velocity_combines_air_vector_and_true_wind(self):
        speed_kmh, track_deg = ground_velocity_from_true_wind(
            airspeed_kmh=100.0,
            track_deg=90.0,
            wind_from_direction_deg=0.0,
            wind_speed_kmh=20.0,
        )

        self.assertAlmostEqual(speed_kmh, 101.980390, places=6)
        self.assertAlmostEqual(track_deg, 101.309932, places=6)

    def test_turn_rate_and_radius_are_inverse_operations(self):
        turn_rate = calculate_turn_rate_deg_s(90.0, 120.0)
        radius = calculate_turn_radius_m(90.0, turn_rate)
        self.assertAlmostEqual(radius, 120.0, places=6)

    def test_advance_heading_turns_left_and_right(self):
        right = advance_heading_deg(90.0, speed_kmh=72.0, turn_radius_m=100.0, dt_s=5.0, turn_direction=1)
        left = advance_heading_deg(90.0, speed_kmh=72.0, turn_radius_m=100.0, dt_s=5.0, turn_direction=-1)

        self.assertGreater(right, 90.0)
        self.assertLess(left, 90.0)

    def test_advance_position_moves_north_for_zero_track(self):
        latitude_deg, longitude_deg = advance_position(
            49.0,
            19.0,
            track_deg=0.0,
            speed_kmh=72.0,
            dt_s=10.0,
        )

        self.assertGreater(latitude_deg, 49.0)
        self.assertAlmostEqual(longitude_deg, 19.0, places=3)

    def test_advance_position_moves_east_for_ninety_degree_track(self):
        latitude_deg, longitude_deg = advance_position(
            49.0,
            19.0,
            track_deg=90.0,
            speed_kmh=72.0,
            dt_s=10.0,
        )

        self.assertAlmostEqual(latitude_deg, 49.0, places=3)
        self.assertGreater(longitude_deg, 19.0)

    def test_bearing_between_points_matches_cardinal_direction(self):
        bearing = bearing_between_points_deg(49.0, 19.0, 50.0, 19.0)
        self.assertAlmostEqual(bearing, 0.0, places=3)


if __name__ == "__main__":
    unittest.main()
