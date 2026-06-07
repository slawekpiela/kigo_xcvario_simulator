"""Deterministic traffic generator relative to ownship."""

from __future__ import annotations

import math

from .contracts import OwnshipState, TrafficContact
from .flight_math import normalize_heading_deg
from .traffic_database import LAB_TRAFFIC_AIRCRAFT_COUNT, traffic_aircraft_for
from .variation import SeededRangeGenerator

AUTO_COLLISION_INTERVAL_S = 10.0
RING_DISTANCES_M = (3000.0, 6000.0, 10000.0, 20000.0, 30000.0)
ALTITUDE_BANDS_M = (-900.0, -620.0, -330.0, -120.0, 180.0, 470.0, 820.0, 1180.0)


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
        if self._uses_collision_course(index, collision_course=collision_course):
            return self._build_collision_contact(ownship, index)

        return self._build_ring_contact(ownship, index)

    def _build_ring_contact(self, ownship: OwnshipState, index: int) -> TrafficContact:
        ring_index = _ring_index_for_contact(index)
        radius_m = RING_DISTANCES_M[ring_index]
        behavior_index = index % len(RING_DISTANCES_M)
        base_bearing_deg = normalize_heading_deg((self._seed * 17 + index * 53) + ownship.track_deg * 0.25)
        orbit_period_s = 140.0 + ring_index * 110.0 + (index % 7) * 23.0 + ownship.speed_kmh * 0.12
        orbit_direction = -1.0 if index % 2 else 1.0
        if behavior_index in (2, 3):
            orbit_direction *= 0.55
        angle_deg = normalize_heading_deg(base_bearing_deg + orbit_direction * (self._sim_time_s / orbit_period_s) * 360.0)
        angle_rad = math.radians(angle_deg)

        relative_north_m = math.cos(angle_rad) * radius_m
        relative_east_m = math.sin(angle_rad) * radius_m
        track_deg = self._track_for_behavior(ownship, angle_deg, behavior_index, orbit_direction, index)
        climb_ms = self._climb_for_behavior(index, behavior_index)

        base_relative_altitude_m = ALTITUDE_BANDS_M[index % len(ALTITUDE_BANDS_M)]
        altitude_wave_m = math.sin(math.radians(angle_deg + index * 37.0)) * (35.0 + ring_index * 30.0)
        relative_altitude_m = base_relative_altitude_m + altitude_wave_m + climb_ms * (12.0 + ring_index * 8.0)
        alarm_level = 1 if ring_index == 0 and abs(relative_altitude_m) < 180.0 else 0

        return self._contact(
            index=index,
            relative_north_m=relative_north_m,
            relative_east_m=relative_east_m,
            relative_altitude_m=relative_altitude_m,
            track_deg=track_deg,
            climb_ms=climb_ms,
            alarm_level=alarm_level,
        )

    def _build_collision_contact(self, ownship: OwnshipState, index: int) -> TrafficContact:
        ownship_heading_deg = normalize_heading_deg(ownship.track_deg)
        ownship_heading_rad = math.radians(ownship_heading_deg)
        right_heading_rad = math.radians(normalize_heading_deg(ownship_heading_deg + 90.0))

        cycle_elapsed_s = self._collision_cycle_elapsed_s()
        initial_distance_m = RING_DISTANCES_M[0] + self._fraction(index, "collision_distance") * 650.0
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
            alarm_level=alarm_level,
        )

    def _uses_collision_course(self, index: int, *, collision_course: bool) -> bool:
        if collision_course:
            return index == 0
        if index >= LAB_TRAFFIC_AIRCRAFT_COUNT:
            return False
        return index == self._rotating_collision_index()

    def _rotating_collision_index(self) -> int:
        return int(self._sim_time_s // AUTO_COLLISION_INTERVAL_S) % LAB_TRAFFIC_AIRCRAFT_COUNT

    def _collision_cycle_elapsed_s(self) -> float:
        return self._sim_time_s % AUTO_COLLISION_INTERVAL_S

    def _track_for_behavior(
        self,
        ownship: OwnshipState,
        angle_deg: float,
        behavior_index: int,
        orbit_direction: float,
        index: int,
    ) -> float:
        if behavior_index == 0:
            return normalize_heading_deg(angle_deg + 90.0 * orbit_direction)
        if behavior_index == 1:
            return normalize_heading_deg(angle_deg - 90.0 * orbit_direction)
        if behavior_index == 2:
            return normalize_heading_deg(angle_deg + 180.0)
        if behavior_index == 3:
            return normalize_heading_deg(angle_deg)
        offset_deg = -45.0 + self._fraction(index, "parallel_offset") * 90.0
        return normalize_heading_deg(ownship.track_deg + offset_deg)

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
            alarm_level=alarm_level,
            aircraft_id=aircraft.device_id,
            competition_id=aircraft.competition_id,
            registration=aircraft.registration,
            aircraft_model=aircraft.aircraft_model,
        )

    def _fraction(self, index: int, salt: str) -> float:
        generator = SeededRangeGenerator(
            seed=self._seed,
            minimum=0.0,
            maximum=1.0,
            salt=f"traffic:{index}:{salt}",
            interpolation_ticks=1,
        )
        return generator.value_at(0)


def _ring_index_for_contact(index: int) -> int:
    ring_offset = index - LAB_TRAFFIC_AIRCRAFT_COUNT if index >= LAB_TRAFFIC_AIRCRAFT_COUNT else index
    return ring_offset % len(RING_DISTANCES_M)
