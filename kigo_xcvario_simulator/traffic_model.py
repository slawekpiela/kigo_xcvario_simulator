"""Deterministic traffic generator relative to ownship."""

from __future__ import annotations

import math

from .contracts import OwnshipState, TrafficContact
from .flight_math import normalize_heading_deg
from .traffic_database import traffic_aircraft_for
from .variation import SeededRangeGenerator


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

        base_bearing_deg = normalize_heading_deg((self._seed * 17 + index * 71) + ownship.track_deg * 0.25)
        orbit_period_s = 55.0 + index * 12.0 + ownship.speed_kmh * 0.05
        radius_m = 500.0 + self._fraction(index, "radius") * 900.0
        angle_deg = normalize_heading_deg(base_bearing_deg + (self._sim_time_s / orbit_period_s) * 360.0)
        angle_rad = math.radians(angle_deg)

        relative_north_m = math.cos(angle_rad) * radius_m
        relative_east_m = math.sin(angle_rad) * radius_m
        track_deg = normalize_heading_deg(angle_deg + 90.0)
        climb_ms = SeededRangeGenerator(
            seed=self._seed,
            minimum=-1.5,
            maximum=2.5,
            salt=f"traffic:{index}:climb",
            interpolation_ticks=4,
        ).value_at(self._tick_index)

        base_relative_altitude_m = -180.0 + self._fraction(index, "altitude") * 360.0
        relative_altitude_m = base_relative_altitude_m + climb_ms * 6.0
        alarm_level = 1 if abs(relative_altitude_m) < 150.0 and radius_m < 700.0 else 0

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

    def _build_collision_contact(self, ownship: OwnshipState, index: int) -> TrafficContact:
        ownship_heading_deg = normalize_heading_deg(ownship.track_deg)
        ownship_heading_rad = math.radians(ownship_heading_deg)
        right_heading_rad = math.radians(normalize_heading_deg(ownship_heading_deg + 90.0))

        initial_distance_m = 1800.0 + self._fraction(index, "collision_distance") * 700.0
        traffic_speed_kmh = 85.0 + self._fraction(index, "collision_speed") * 35.0
        closure_speed_ms = max(15.0, ownship.speed_kmh / 3.6) + traffic_speed_kmh / 3.6
        along_track_m = initial_distance_m - self._sim_time_s * closure_speed_ms
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
