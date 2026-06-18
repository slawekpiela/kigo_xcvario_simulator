"""Deterministic traffic generator relative to ownship."""

from __future__ import annotations

import math

from .contracts import OwnshipState, TrafficContact
from .flight_math import normalize_heading_deg
from .traffic_database import traffic_aircraft_for
from .variation import SeededRangeGenerator

AUTO_COLLISION_INTERVAL_S = 10.0
MIN_TRAFFIC_RADIUS_M = 5000.0
MAX_TRAFFIC_RADIUS_M = 30000.0
TRAFFIC_RADIUS_MARGIN_M = 100.0
ORBIT_PERIOD_RANGE_S = (300.0, 900.0)
TRAFFIC_SPEED_RANGE_MS = (0.5, 5.0)
CLIMBING_ORBIT_CONTACT_COUNT = 4
COLLISION_INITIAL_DISTANCE_M = 3000.0
ALTITUDE_BANDS_M = (-900.0, -620.0, -330.0, -120.0, 180.0, 470.0, 820.0, 1180.0)
ORBIT_BEHAVIOR_COUNT = 5


class TrafficGenerator:
    """Produces deterministic FLARM-like contacts around the ownship."""

    def __init__(self, *, seed: int) -> None:
        self._seed = int(seed)
        self._sim_time_s = 0.0
        self._tick_index = 0

    def reset(self) -> None:
        self._sim_time_s = 0.0
        self._tick_index = 0

    def reseed(self, seed: int) -> None:
        self._seed = int(seed)
        self.reset()

    def step(
        self,
        ownship: OwnshipState,
        dt_s: float,
        *,
        contact_count: int,
        collision_course: bool = False,
    ) -> tuple[TrafficContact, ...]:
        if dt_s < 0.0:
            raise ValueError("dt_s must be >= 0.")
        if contact_count <= 0:
            self._sim_time_s += max(dt_s, 0.0)
            self._tick_index += 1
            return ()

        self._sim_time_s += dt_s
        contacts = tuple(
            self._build_contact(ownship, index, collision_course=collision_course)
            for index in range(contact_count)
        )
        self._tick_index += 1
        return contacts

    def _build_contact(
        self,
        ownship: OwnshipState,
        index: int,
        *,
        collision_course: bool,
    ) -> TrafficContact:
        if collision_course and index == 0:
            return self._build_collision_contact(ownship, index)

        return self._build_orbiting_contact(ownship, index)

    def _build_orbiting_contact(self, ownship: OwnshipState, index: int) -> TrafficContact:
        speed_ms = self._traffic_speed_ms(index)
        orbit_period_s = ORBIT_PERIOD_RANGE_S[0] + self._fraction(index, "orbit_period") * (
            ORBIT_PERIOD_RANGE_S[1] - ORBIT_PERIOD_RANGE_S[0]
        )
        turn_radius_m = speed_ms * orbit_period_s / (math.pi * 2.0)
        max_center_distance_m = MAX_TRAFFIC_RADIUS_M - TRAFFIC_RADIUS_MARGIN_M - turn_radius_m
        min_center_distance_m = MIN_TRAFFIC_RADIUS_M + turn_radius_m
        center_distance_m = min_center_distance_m + self._fraction(index, "center_distance") * (
            max_center_distance_m - min_center_distance_m
        )
        center_bearing_deg = normalize_heading_deg(self._seed * 17.0 + index * 121.0 + ownship.track_deg * 0.20)
        center_bearing_rad = math.radians(center_bearing_deg)
        center_north_m = math.cos(center_bearing_rad) * center_distance_m
        center_east_m = math.sin(center_bearing_rad) * center_distance_m

        turn_direction = 1.0 if index % 2 == 0 else -1.0
        angular_speed_deg_s = math.degrees(speed_ms / turn_radius_m)
        orbit_angle_deg = normalize_heading_deg(
            center_bearing_deg + 70.0 + turn_direction * self._sim_time_s * angular_speed_deg_s
        )
        orbit_angle_rad = math.radians(orbit_angle_deg)

        relative_north_m = center_north_m + math.cos(orbit_angle_rad) * turn_radius_m
        relative_east_m = center_east_m + math.sin(orbit_angle_rad) * turn_radius_m
        track_deg = normalize_heading_deg(orbit_angle_deg + 90.0 * turn_direction)
        behavior_index = index % ORBIT_BEHAVIOR_COUNT
        climb_ms = self._orbit_climb_ms(index, behavior_index)

        base_relative_altitude_m = ALTITUDE_BANDS_M[index % len(ALTITUDE_BANDS_M)]
        altitude_wave_m = math.sin(math.radians(orbit_angle_deg + index * 37.0)) * 55.0
        relative_altitude_m = base_relative_altitude_m + altitude_wave_m + climb_ms * 18.0

        return self._contact(
            index=index,
            relative_north_m=relative_north_m,
            relative_east_m=relative_east_m,
            relative_altitude_m=relative_altitude_m,
            track_deg=track_deg,
            climb_ms=climb_ms,
            speed_ms=speed_ms,
            alarm_level=self._alarm_level(relative_north_m, relative_east_m, relative_altitude_m),
        )

    def _build_collision_contact(self, ownship: OwnshipState, index: int) -> TrafficContact:
        ownship_heading_deg = normalize_heading_deg(ownship.track_deg)
        ownship_heading_rad = math.radians(ownship_heading_deg)
        right_heading_rad = math.radians(normalize_heading_deg(ownship_heading_deg + 90.0))

        cycle_elapsed_s = self._collision_cycle_elapsed_s()
        initial_distance_m = COLLISION_INITIAL_DISTANCE_M + self._fraction(index, "collision_distance") * 650.0
        traffic_speed_kmh = 85.0 + self._fraction(index, "collision_speed") * 35.0
        closure_speed_ms = max(15.0, ownship.speed_kmh / 3.6) + traffic_speed_kmh / 3.6
        along_track_m = initial_distance_m - cycle_elapsed_s * closure_speed_ms
        lateral_offset_m = -20.0 + self._fraction(index, "collision_lateral") * 40.0

        relative_north_m = math.cos(ownship_heading_rad) * along_track_m + math.cos(right_heading_rad) * lateral_offset_m
        relative_east_m = math.sin(ownship_heading_rad) * along_track_m + math.sin(right_heading_rad) * lateral_offset_m
        track_deg = normalize_heading_deg(ownship_heading_deg + 180.0)
        climb_ms = SeededRangeGenerator(
            seed=self._seed,
            minimum=-0.4,
            maximum=0.4,
            salt=f"traffic:{index}:collision:climb",
            interpolation_ticks=3,
        ).value_at(self._tick_index)

        relative_altitude_m = (-35.0 + self._fraction(index, "collision_altitude") * 70.0) + climb_ms * 3.0
        separation_m = math.hypot(along_track_m, lateral_offset_m)
        if separation_m < 250.0 and abs(relative_altitude_m) < 60.0:
            alarm_level = 3
        elif separation_m < 700.0 and abs(relative_altitude_m) < 120.0:
            alarm_level = 2
        else:
            alarm_level = 1

        return self._contact(
            index=index,
            relative_north_m=relative_north_m,
            relative_east_m=relative_east_m,
            relative_altitude_m=relative_altitude_m,
            track_deg=track_deg,
            climb_ms=climb_ms,
            speed_ms=traffic_speed_kmh / 3.6,
            alarm_level=alarm_level,
        )

    def _traffic_speed_ms(self, index: int) -> float:
        return TRAFFIC_SPEED_RANGE_MS[0] + self._fraction(index, "speed") * (
            TRAFFIC_SPEED_RANGE_MS[1] - TRAFFIC_SPEED_RANGE_MS[0]
        )

    def _orbit_climb_ms(self, index: int, behavior_index: int) -> float:
        if index < CLIMBING_ORBIT_CONTACT_COUNT:
            return 0.5 + self._fraction(index, "climbing_orbit_climb") * 1.7
        return self._climb_for_behavior(index, behavior_index)

    def _collision_cycle_elapsed_s(self) -> float:
        return self._sim_time_s % AUTO_COLLISION_INTERVAL_S

    def _climb_for_behavior(self, index: int, behavior_index: int) -> float:
        climb_ranges = (
            (-0.5, 0.9),
            (-1.4, 0.1),
            (-0.2, 1.7),
            (-2.1, -0.2),
            (0.2, 2.4),
        )
        minimum, maximum = climb_ranges[behavior_index]
        return SeededRangeGenerator(
            seed=self._seed,
            minimum=minimum,
            maximum=maximum,
            salt=f"traffic:{index}:behavior:{behavior_index}:climb",
            interpolation_ticks=5,
        ).value_at(self._tick_index)

    def _contact(
        self,
        *,
        index: int,
        relative_north_m: float,
        relative_east_m: float,
        relative_altitude_m: float,
        track_deg: float,
        climb_ms: float,
        speed_ms: float,
        alarm_level: int,
    ) -> TrafficContact:
        aircraft = traffic_aircraft_for(self._seed, index)
        return TrafficContact(
            contact_id=f"TFC-{index + 1:02d}",
            relative_north_m=relative_north_m,
            relative_east_m=relative_east_m,
            relative_altitude_m=relative_altitude_m,
            track_deg=track_deg,
            climb_ms=climb_ms,
            speed_ms=speed_ms,
            alarm_level=alarm_level,
            aircraft_id=aircraft.device_id,
            competition_id=aircraft.competition_id,
            registration=aircraft.registration,
            aircraft_model=aircraft.aircraft_model,
        )

    def _alarm_level(self, relative_north_m: float, relative_east_m: float, relative_altitude_m: float) -> int:
        distance_m = math.hypot(relative_north_m, relative_east_m)
        if distance_m < 700.0 and abs(relative_altitude_m) < 120.0:
            return 2
        if distance_m < 2500.0 and abs(relative_altitude_m) < 180.0:
            return 1
        return 0

    def _fraction(self, index: int, salt: str) -> float:
        generator = SeededRangeGenerator(
            seed=self._seed,
            minimum=0.0,
            maximum=1.0,
            salt=f"traffic:{index}:{salt}",
            interpolation_ticks=1,
        )
        return generator.value_at(0)
