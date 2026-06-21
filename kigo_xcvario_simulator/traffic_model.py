"""Deterministic traffic generator around an anchor, reported relative to ownship."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .contracts import (
    TRAFFIC_CIRCLING_RADIUS_MAX_M,
    TRAFFIC_CIRCLING_RADIUS_MIN_M,
    TRAFFIC_MOTION_MODES,
    TRAFFIC_MOTION_ORBIT,
    TRAFFIC_MOTION_STRAIGHT,
    OwnshipState,
    TrafficContact,
)
from .flight_math import normalize_heading_deg
from .traffic_database import FLARM_TRAFFIC_AIRCRAFT, FlarmTrafficAircraft, traffic_aircraft_for
from .variation import SeededRangeGenerator

AUTO_COLLISION_INTERVAL_S = 10.0
MIN_TRAFFIC_RADIUS_M = 5000.0
MAX_TRAFFIC_RADIUS_M = 30000.0
TRAFFIC_RADIUS_MARGIN_M = 100.0
TRAFFIC_SPEED_RANGE_KMH = (100.0, 200.0)
TRAFFIC_SPEED_RANGE_MS = (
    TRAFFIC_SPEED_RANGE_KMH[0] / 3.6,
    TRAFFIC_SPEED_RANGE_KMH[1] / 3.6,
)
TRAFFIC_CLIMB_RANGE_MS = (0.51, 4.0)
COLLISION_INITIAL_DISTANCE_M = 3000.0
ALTITUDE_BANDS_M = (-900.0, -620.0, -330.0, -120.0, 180.0, 470.0, 820.0, 1180.0)
STRAIGHT_PATH_HALF_LENGTH_RANGE_M = (900.0, 2600.0)
MIN_CIRCLING_RADIUS_M = 100.0
MAX_CIRCLING_RADIUS_M = (MAX_TRAFFIC_RADIUS_M - TRAFFIC_RADIUS_MARGIN_M - MIN_TRAFFIC_RADIUS_M) / 2.0
ORBIT_STRAIGHT_DURATION_S = 120.0
ORBIT_GAIN_RANGE_M = (300.0, 1000.0)
METERS_PER_DEGREE_LATITUDE = 111320.0


@dataclass
class _OrbitingContactState:
    absolute_north_m: float
    absolute_east_m: float
    absolute_altitude_m: float
    speed_ms: float
    climb_ms: float
    track_deg: float
    phase: str
    phase_elapsed_s: float
    cycle_index: int
    center_north_m: float
    center_east_m: float
    semi_major_m: float
    semi_minor_m: float
    ellipse_rotation_rad: float
    orbit_angle_rad: float
    turn_direction: float
    climb_target_m: float
    climb_gained_m: float


class TrafficGenerator:
    """Produces deterministic FLARM-like contacts around the ownship."""

    def __init__(self, *, seed: int, aircraft: tuple[FlarmTrafficAircraft, ...] | None = None) -> None:
        self._seed = int(seed)
        self._aircraft = aircraft or FLARM_TRAFFIC_AIRCRAFT
        self._sim_time_s = 0.0
        self._tick_index = 0
        self._anchor_latitude_deg: float | None = None
        self._anchor_longitude_deg: float | None = None
        self._anchor_altitude_m: float = 0.0
        self._anchor_track_deg: float = 0.0
        self._orbit_states: dict[int, _OrbitingContactState] = {}
        self._last_motion_mode = TRAFFIC_MOTION_ORBIT
        self._last_radius_range = (
            TRAFFIC_CIRCLING_RADIUS_MIN_M,
            TRAFFIC_CIRCLING_RADIUS_MAX_M,
        )

    def reset(self) -> None:
        self._sim_time_s = 0.0
        self._tick_index = 0
        self._anchor_latitude_deg = None
        self._anchor_longitude_deg = None
        self._anchor_altitude_m = 0.0
        self._anchor_track_deg = 0.0
        self._orbit_states = {}
        self._last_motion_mode = TRAFFIC_MOTION_ORBIT
        self._last_radius_range = (
            TRAFFIC_CIRCLING_RADIUS_MIN_M,
            TRAFFIC_CIRCLING_RADIUS_MAX_M,
        )

    def reseed(self, seed: int) -> None:
        self._seed = int(seed)
        self.reset()

    def step(
        self,
        ownship: OwnshipState,
        dt_s: float,
        *,
        anchor: OwnshipState | None = None,
        contact_count: int,
        collision_course: bool = False,
        motion_mode: str = TRAFFIC_MOTION_ORBIT,
        circling_radius_min_m: float | None = TRAFFIC_CIRCLING_RADIUS_MIN_M,
        circling_radius_max_m: float | None = TRAFFIC_CIRCLING_RADIUS_MAX_M,
    ) -> tuple[TrafficContact, ...]:
        if dt_s < 0.0:
            raise ValueError("dt_s must be >= 0.")
        if contact_count <= 0:
            self._sim_time_s += max(dt_s, 0.0)
            self._tick_index += 1
            return ()

        self._sim_time_s += dt_s
        self._ensure_anchor(anchor or ownship)
        resolved_motion_mode = normalize_traffic_motion_mode(motion_mode)
        circling_radius_min_m, circling_radius_max_m = normalize_traffic_circling_radius_range(
            circling_radius_min_m,
            circling_radius_max_m,
        )
        radius_range = (circling_radius_min_m, circling_radius_max_m)
        if resolved_motion_mode != self._last_motion_mode or radius_range != self._last_radius_range:
            self._orbit_states = {}
            self._last_motion_mode = resolved_motion_mode
            self._last_radius_range = radius_range
        contacts = tuple(
            self._build_contact(
                ownship,
                index,
                dt_s=dt_s,
                collision_course=collision_course,
                motion_mode=resolved_motion_mode,
                circling_radius_min_m=circling_radius_min_m,
                circling_radius_max_m=circling_radius_max_m,
            )
            for index in range(contact_count)
        )
        self._tick_index += 1
        return contacts

    def _build_contact(
        self,
        ownship: OwnshipState,
        index: int,
        *,
        dt_s: float,
        collision_course: bool,
        motion_mode: str,
        circling_radius_min_m: float,
        circling_radius_max_m: float,
    ) -> TrafficContact:
        if collision_course and index == 0:
            return self._build_collision_contact(ownship, index)

        if motion_mode == TRAFFIC_MOTION_STRAIGHT:
            return self._build_straight_contact(ownship, index)

        return self._build_orbiting_contact(
            ownship,
            index,
            circling_radius_min_m=circling_radius_min_m,
            circling_radius_max_m=circling_radius_max_m,
            dt_s=dt_s,
        )

    def _build_orbiting_contact(
        self,
        ownship: OwnshipState,
        index: int,
        *,
        circling_radius_min_m: float,
        circling_radius_max_m: float,
        dt_s: float,
    ) -> TrafficContact:
        state = self._orbit_states.get(index)
        if state is None:
            state = self._create_orbiting_state(
                index,
                circling_radius_min_m=circling_radius_min_m,
                circling_radius_max_m=circling_radius_max_m,
            )
            self._orbit_states[index] = state
        self._advance_orbiting_state(state, index, dt_s, circling_radius_min_m, circling_radius_max_m)
        ownship_north_m, ownship_east_m = self._ownship_offset_m(ownship)
        relative_north_m = state.absolute_north_m - ownship_north_m
        relative_east_m = state.absolute_east_m - ownship_east_m
        relative_altitude_m = state.absolute_altitude_m - ownship.gps_altitude_m
        climb_ms = state.climb_ms if state.phase == "orbit" else 0.0

        return self._contact(
            index=index,
            relative_north_m=relative_north_m,
            relative_east_m=relative_east_m,
            relative_altitude_m=relative_altitude_m,
            track_deg=state.track_deg,
            climb_ms=climb_ms,
            speed_ms=state.speed_ms,
            alarm_level=self._alarm_level(relative_north_m, relative_east_m, relative_altitude_m),
        )

    def _build_straight_contact(self, ownship: OwnshipState, index: int) -> TrafficContact:
        speed_ms = self._traffic_speed_ms(index)
        half_length_m = STRAIGHT_PATH_HALF_LENGTH_RANGE_M[0] + self._fraction(index, "straight_length") * (
            STRAIGHT_PATH_HALF_LENGTH_RANGE_M[1] - STRAIGHT_PATH_HALF_LENGTH_RANGE_M[0]
        )
        max_center_distance_m = math.sqrt(
            max(0.0, (MAX_TRAFFIC_RADIUS_M - TRAFFIC_RADIUS_MARGIN_M) ** 2 - half_length_m * half_length_m)
        )
        center_distance_m = MIN_TRAFFIC_RADIUS_M + self._fraction(index, "straight_center") * (
            max_center_distance_m - MIN_TRAFFIC_RADIUS_M
        )
        center_bearing_deg = normalize_heading_deg(self._seed * 29.0 + index * 73.0 + self._anchor_track_deg * 0.14)
        center_bearing_rad = math.radians(center_bearing_deg)
        route_bearing_deg = normalize_heading_deg(center_bearing_deg + 90.0)
        route_bearing_rad = math.radians(route_bearing_deg)

        cycle_length_m = half_length_m * 4.0
        cycle_distance_m = (
            self._sim_time_s * speed_ms + self._fraction(index, "straight_phase") * cycle_length_m
        ) % cycle_length_m
        if cycle_distance_m <= half_length_m * 2.0:
            along_m = -half_length_m + cycle_distance_m
            track_deg = route_bearing_deg
        else:
            along_m = half_length_m - (cycle_distance_m - half_length_m * 2.0)
            track_deg = normalize_heading_deg(route_bearing_deg + 180.0)

        absolute_north_m = math.cos(center_bearing_rad) * center_distance_m + math.cos(route_bearing_rad) * along_m
        absolute_east_m = math.sin(center_bearing_rad) * center_distance_m + math.sin(route_bearing_rad) * along_m
        climb_ms = self._orbit_climb_ms(index)
        base_relative_altitude_m = ALTITUDE_BANDS_M[index % len(ALTITUDE_BANDS_M)]
        altitude_wave_m = math.sin(math.radians(track_deg + self._sim_time_s * 1.7 + index * 37.0)) * 55.0
        absolute_altitude_m = self._anchor_altitude_m + base_relative_altitude_m + altitude_wave_m + climb_ms * 18.0
        ownship_north_m, ownship_east_m = self._ownship_offset_m(ownship)
        relative_north_m = absolute_north_m - ownship_north_m
        relative_east_m = absolute_east_m - ownship_east_m
        relative_altitude_m = absolute_altitude_m - ownship.gps_altitude_m

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

    def _ensure_anchor(self, ownship: OwnshipState) -> None:
        if self._anchor_latitude_deg is not None and self._anchor_longitude_deg is not None:
            return
        self._anchor_latitude_deg = ownship.latitude_deg
        self._anchor_longitude_deg = ownship.longitude_deg
        self._anchor_altitude_m = ownship.gps_altitude_m
        self._anchor_track_deg = normalize_heading_deg(ownship.track_deg)

    def _ownship_offset_m(self, ownship: OwnshipState) -> tuple[float, float]:
        if self._anchor_latitude_deg is None or self._anchor_longitude_deg is None:
            return (0.0, 0.0)
        north_m = (ownship.latitude_deg - self._anchor_latitude_deg) * METERS_PER_DEGREE_LATITUDE
        longitude_scale_m = METERS_PER_DEGREE_LATITUDE * math.cos(math.radians(self._anchor_latitude_deg))
        east_m = (ownship.longitude_deg - self._anchor_longitude_deg) * longitude_scale_m
        return (north_m, east_m)

    def _create_orbiting_state(
        self,
        index: int,
        *,
        circling_radius_min_m: float,
        circling_radius_max_m: float,
    ) -> _OrbitingContactState:
        semi_major_m = self._circling_radius_m(index, circling_radius_min_m, circling_radius_max_m)
        semi_minor_m = self._ellipse_semi_minor_m(index, 0, semi_major_m)
        ellipse_rotation_rad = self._ellipse_rotation_rad(index, 0)
        turn_direction = self._turn_direction(index, 0)
        orbit_angle_rad = math.radians(normalize_heading_deg(47.0 + index * 19.0 + self._fraction(index, "angle") * 360.0))
        max_straight_reserve_m = TRAFFIC_SPEED_RANGE_MS[1] * ORBIT_STRAIGHT_DURATION_S
        min_center_distance_m = MIN_TRAFFIC_RADIUS_M + semi_major_m + TRAFFIC_RADIUS_MARGIN_M
        max_center_distance_m = MAX_TRAFFIC_RADIUS_M - TRAFFIC_RADIUS_MARGIN_M - semi_major_m - max_straight_reserve_m
        if max_center_distance_m < min_center_distance_m:
            max_center_distance_m = MAX_TRAFFIC_RADIUS_M - TRAFFIC_RADIUS_MARGIN_M - semi_major_m
        if max_center_distance_m < min_center_distance_m:
            max_center_distance_m = min_center_distance_m
        center_distance_m = min_center_distance_m + self._fraction(index, "orbit_center") * (
            max_center_distance_m - min_center_distance_m
        )
        center_bearing_deg = normalize_heading_deg(self._seed * 31.0 + index * 71.0 + self._anchor_track_deg * 0.2)
        center_bearing_rad = math.radians(center_bearing_deg)
        center_north_m = math.cos(center_bearing_rad) * center_distance_m
        center_east_m = math.sin(center_bearing_rad) * center_distance_m
        offset_north_m, offset_east_m = self._ellipse_offset(
            semi_major_m,
            semi_minor_m,
            ellipse_rotation_rad,
            orbit_angle_rad,
        )
        absolute_north_m = center_north_m + offset_north_m
        absolute_east_m = center_east_m + offset_east_m
        base_relative_altitude_m = ALTITUDE_BANDS_M[index % len(ALTITUDE_BANDS_M)]
        altitude_wave_m = math.sin(math.radians(center_bearing_deg + index * 41.0)) * 55.0
        absolute_altitude_m = self._anchor_altitude_m + base_relative_altitude_m + altitude_wave_m
        speed_ms = self._traffic_speed_ms(index)
        climb_ms = self._orbit_climb_ms(index, 0)
        track_deg = self._ellipse_track_deg(
            semi_major_m,
            semi_minor_m,
            ellipse_rotation_rad,
            orbit_angle_rad,
            turn_direction,
        )

        return _OrbitingContactState(
            absolute_north_m=absolute_north_m,
            absolute_east_m=absolute_east_m,
            absolute_altitude_m=absolute_altitude_m,
            speed_ms=speed_ms,
            climb_ms=climb_ms,
            track_deg=track_deg,
            phase="orbit",
            phase_elapsed_s=0.0,
            cycle_index=0,
            center_north_m=center_north_m,
            center_east_m=center_east_m,
            semi_major_m=semi_major_m,
            semi_minor_m=semi_minor_m,
            ellipse_rotation_rad=ellipse_rotation_rad,
            orbit_angle_rad=orbit_angle_rad,
            turn_direction=turn_direction,
            climb_target_m=self._orbit_gain_m(index, 0),
            climb_gained_m=0.0,
        )

    def _advance_orbiting_state(
        self,
        state: _OrbitingContactState,
        index: int,
        dt_s: float,
        circling_radius_min_m: float,
        circling_radius_max_m: float,
    ) -> None:
        remaining_s = dt_s
        while remaining_s > 1e-9:
            if state.phase == "orbit":
                climb_remaining_m = max(0.0, state.climb_target_m - state.climb_gained_m)
                if climb_remaining_m <= 1e-6:
                    state.phase = "straight"
                    state.phase_elapsed_s = 0.0
                    continue
                time_to_gain_s = climb_remaining_m / max(state.climb_ms, 1e-6)
                step_s = min(remaining_s, time_to_gain_s)
                self._advance_ellipse_motion(state, step_s)
                remaining_s -= step_s
                if step_s >= time_to_gain_s - 1e-9:
                    state.climb_gained_m = state.climb_target_m
                    state.phase = "straight"
                    state.phase_elapsed_s = 0.0
            else:
                straight_remaining_s = max(0.0, ORBIT_STRAIGHT_DURATION_S - state.phase_elapsed_s)
                if straight_remaining_s <= 1e-6:
                    self._start_next_orbit(
                        state,
                        index,
                        circling_radius_min_m=circling_radius_min_m,
                        circling_radius_max_m=circling_radius_max_m,
                    )
                    continue
                step_s = min(remaining_s, straight_remaining_s)
                self._advance_straight_motion(state, step_s)
                state.phase_elapsed_s += step_s
                remaining_s -= step_s
                if state.phase_elapsed_s >= ORBIT_STRAIGHT_DURATION_S - 1e-9:
                    self._start_next_orbit(
                        state,
                        index,
                        circling_radius_min_m=circling_radius_min_m,
                        circling_radius_max_m=circling_radius_max_m,
                    )

    def _advance_ellipse_motion(self, state: _OrbitingContactState, dt_s: float) -> None:
        remaining_s = dt_s
        while remaining_s > 1e-9:
            step_s = min(remaining_s, 5.0)
            per_radian_m = math.hypot(
                state.semi_major_m * math.sin(state.orbit_angle_rad),
                state.semi_minor_m * math.cos(state.orbit_angle_rad),
            )
            angular_speed_rad_s = state.speed_ms / max(per_radian_m, 1.0)
            state.orbit_angle_rad += state.turn_direction * angular_speed_rad_s * step_s
            state.absolute_altitude_m += state.climb_ms * step_s
            state.climb_gained_m += state.climb_ms * step_s
            state.phase_elapsed_s += step_s
            remaining_s -= step_s
        self._set_ellipse_position_and_track(state)

    def _advance_straight_motion(self, state: _OrbitingContactState, dt_s: float) -> None:
        track_deg = self._bounded_straight_track_deg(state, dt_s)
        state.track_deg = track_deg
        track_rad = math.radians(track_deg)
        state.absolute_north_m += math.cos(track_rad) * state.speed_ms * dt_s
        state.absolute_east_m += math.sin(track_rad) * state.speed_ms * dt_s

    def _bounded_straight_track_deg(self, state: _OrbitingContactState, dt_s: float) -> float:
        track_rad = math.radians(state.track_deg)
        next_north_m = state.absolute_north_m + math.cos(track_rad) * state.speed_ms * dt_s
        next_east_m = state.absolute_east_m + math.sin(track_rad) * state.speed_ms * dt_s
        next_distance_m = math.hypot(next_north_m, next_east_m)
        if MIN_TRAFFIC_RADIUS_M <= next_distance_m <= MAX_TRAFFIC_RADIUS_M - TRAFFIC_RADIUS_MARGIN_M:
            return state.track_deg

        radial_bearing_deg = normalize_heading_deg(math.degrees(math.atan2(state.absolute_east_m, state.absolute_north_m)))
        if next_distance_m > MAX_TRAFFIC_RADIUS_M - TRAFFIC_RADIUS_MARGIN_M:
            return normalize_heading_deg(radial_bearing_deg + 180.0)
        return radial_bearing_deg

    def _start_next_orbit(
        self,
        state: _OrbitingContactState,
        index: int,
        *,
        circling_radius_min_m: float,
        circling_radius_max_m: float,
    ) -> None:
        state.cycle_index += 1
        state.phase = "orbit"
        state.phase_elapsed_s = 0.0
        state.semi_major_m = self._circling_radius_m(index, circling_radius_min_m, circling_radius_max_m)
        state.semi_minor_m = self._ellipse_semi_minor_m(index, state.cycle_index, state.semi_major_m)
        state.ellipse_rotation_rad = self._ellipse_rotation_rad(index, state.cycle_index)
        state.turn_direction = self._turn_direction(index, state.cycle_index)
        state.orbit_angle_rad = math.radians(
            normalize_heading_deg(67.0 + index * 23.0 + state.cycle_index * 31.0 + self._fraction(index, "next_angle") * 360.0)
        )
        offset_north_m, offset_east_m = self._ellipse_offset(
            state.semi_major_m,
            state.semi_minor_m,
            state.ellipse_rotation_rad,
            state.orbit_angle_rad,
        )
        state.center_north_m = state.absolute_north_m - offset_north_m
        state.center_east_m = state.absolute_east_m - offset_east_m
        self._constrain_orbit_center(state)
        state.climb_ms = self._orbit_climb_ms(index, state.cycle_index)
        state.climb_target_m = self._orbit_gain_m(index, state.cycle_index)
        state.climb_gained_m = 0.0
        self._set_ellipse_position_and_track(state)

    def _constrain_orbit_center(self, state: _OrbitingContactState) -> None:
        min_center_distance_m = MIN_TRAFFIC_RADIUS_M + state.semi_major_m
        max_center_distance_m = MAX_TRAFFIC_RADIUS_M - TRAFFIC_RADIUS_MARGIN_M - state.semi_major_m
        if max_center_distance_m < min_center_distance_m:
            max_center_distance_m = min_center_distance_m
        center_distance_m = math.hypot(state.center_north_m, state.center_east_m)
        target_distance_m = min(max(center_distance_m, min_center_distance_m), max_center_distance_m)
        if center_distance_m <= 1e-6:
            state.center_north_m = target_distance_m
            state.center_east_m = 0.0
            return
        scale = target_distance_m / center_distance_m
        state.center_north_m *= scale
        state.center_east_m *= scale

    def _set_ellipse_position_and_track(self, state: _OrbitingContactState) -> None:
        offset_north_m, offset_east_m = self._ellipse_offset(
            state.semi_major_m,
            state.semi_minor_m,
            state.ellipse_rotation_rad,
            state.orbit_angle_rad,
        )
        state.absolute_north_m = state.center_north_m + offset_north_m
        state.absolute_east_m = state.center_east_m + offset_east_m
        state.track_deg = self._ellipse_track_deg(
            state.semi_major_m,
            state.semi_minor_m,
            state.ellipse_rotation_rad,
            state.orbit_angle_rad,
            state.turn_direction,
        )

    def _ellipse_offset(
        self,
        semi_major_m: float,
        semi_minor_m: float,
        rotation_rad: float,
        angle_rad: float,
    ) -> tuple[float, float]:
        x_m = math.cos(angle_rad) * semi_major_m
        y_m = math.sin(angle_rad) * semi_minor_m
        return (
            x_m * math.cos(rotation_rad) - y_m * math.sin(rotation_rad),
            x_m * math.sin(rotation_rad) + y_m * math.cos(rotation_rad),
        )

    def _ellipse_track_deg(
        self,
        semi_major_m: float,
        semi_minor_m: float,
        rotation_rad: float,
        angle_rad: float,
        turn_direction: float,
    ) -> float:
        dx_m = -math.sin(angle_rad) * semi_major_m * turn_direction
        dy_m = math.cos(angle_rad) * semi_minor_m * turn_direction
        north_m = dx_m * math.cos(rotation_rad) - dy_m * math.sin(rotation_rad)
        east_m = dx_m * math.sin(rotation_rad) + dy_m * math.cos(rotation_rad)
        return normalize_heading_deg(math.degrees(math.atan2(east_m, north_m)))

    def _traffic_speed_ms(self, index: int) -> float:
        return TRAFFIC_SPEED_RANGE_MS[0] + self._fraction(index, "speed") * (
            TRAFFIC_SPEED_RANGE_MS[1] - TRAFFIC_SPEED_RANGE_MS[0]
        )

    def _circling_radius_m(self, index: int, minimum_m: float, maximum_m: float) -> float:
        return minimum_m + self._fraction(index, "circling_radius") * (maximum_m - minimum_m)

    def _ellipse_semi_minor_m(self, index: int, cycle_index: int, semi_major_m: float) -> float:
        return semi_major_m * (0.91 + self._fraction(index, f"ellipse_ratio:{cycle_index}") * 0.07)

    def _ellipse_rotation_rad(self, index: int, cycle_index: int) -> float:
        return math.radians(normalize_heading_deg(self._seed * 17.0 + index * 29.0 + cycle_index * 43.0))

    def _turn_direction(self, index: int, cycle_index: int) -> float:
        return 1.0 if (index + cycle_index + self._seed) % 2 == 0 else -1.0

    def _orbit_gain_m(self, index: int, cycle_index: int) -> float:
        return ORBIT_GAIN_RANGE_M[0] + self._fraction(index, f"orbit_gain:{cycle_index}") * (
            ORBIT_GAIN_RANGE_M[1] - ORBIT_GAIN_RANGE_M[0]
        )

    def _orbit_climb_ms(self, index: int, cycle_index: int = 0) -> float:
        return SeededRangeGenerator(
            seed=self._seed,
            minimum=TRAFFIC_CLIMB_RANGE_MS[0],
            maximum=TRAFFIC_CLIMB_RANGE_MS[1],
            salt=f"traffic:{index}:orbit:{cycle_index}:climb",
            interpolation_ticks=5,
        ).value_at(self._tick_index)

    def _collision_cycle_elapsed_s(self) -> float:
        return self._sim_time_s % AUTO_COLLISION_INTERVAL_S

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
        aircraft = traffic_aircraft_for(self._seed, index, aircraft=self._aircraft)
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


def normalize_traffic_motion_mode(motion_mode: str | None) -> str:
    if motion_mode in TRAFFIC_MOTION_MODES:
        return str(motion_mode)
    return TRAFFIC_MOTION_ORBIT


def normalize_traffic_circling_radius_range(
    minimum_m: float | None,
    maximum_m: float | None,
) -> tuple[float, float]:
    minimum = _finite_or_default(minimum_m, TRAFFIC_CIRCLING_RADIUS_MIN_M)
    maximum = _finite_or_default(maximum_m, TRAFFIC_CIRCLING_RADIUS_MAX_M)
    minimum = min(max(minimum, MIN_CIRCLING_RADIUS_M), MAX_CIRCLING_RADIUS_M)
    maximum = min(max(maximum, MIN_CIRCLING_RADIUS_M), MAX_CIRCLING_RADIUS_M)
    if maximum < minimum:
        minimum, maximum = maximum, minimum
    return minimum, maximum


def _finite_or_default(value: float | None, default: float) -> float:
    if value is None:
        return default
    resolved = float(value)
    if not math.isfinite(resolved):
        return default
    return resolved
