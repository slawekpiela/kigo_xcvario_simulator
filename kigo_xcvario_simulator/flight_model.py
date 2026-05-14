"""Ownship kinematic model for the XCvario simulator."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from .baro import simulation_timestamp_utc, static_pressure_hpa_for_altitude
from .contracts import FlightDirective, OwnshipState, WindState
from .flight_math import advance_heading_deg, advance_position, ground_velocity_from_true_wind, normalize_heading_deg
from .state import FlightPhase
from .variation import SeededRangeGenerator


DEFAULT_HOME_TRACK_DEG = 90.0
DEFAULT_CIRCLING_VARIATION_TICKS = 24
DEFAULT_CIRCLING_SPEED_VARIATION_TICKS = 48
DEFAULT_GLIDER_LAUNCH_VARIATION_TICKS = 12
DEFAULT_GENERIC_VARIATION_TICKS = 8


class FlightModel:
    """Stateful ownship model used by presets and manual mode alike."""

    def __init__(
        self,
        *,
        seed: int,
        home_latitude_deg: float,
        home_longitude_deg: float,
        home_altitude_m: float,
        pressure_reference_qnh_hpa: float,
        device_qnh_hpa: float,
        start_utc: datetime | None = None,
        default_track_deg: float = DEFAULT_HOME_TRACK_DEG,
    ) -> None:
        self._seed = int(seed)
        self._home_latitude_deg = float(home_latitude_deg)
        self._home_longitude_deg = float(home_longitude_deg)
        self._home_altitude_m = float(home_altitude_m)
        self._pressure_reference_qnh_hpa = float(pressure_reference_qnh_hpa)
        self._device_qnh_hpa = float(device_qnh_hpa)
        self._start_utc = self._normalize_utc(start_utc or datetime.now(timezone.utc))
        self._default_track_deg = normalize_heading_deg(default_track_deg)
        self._elapsed_s = 0.0
        self._active_directive_key: tuple[object, ...] | None = None
        self._active_variation_tick_index = 0
        self._active_speed_directive_key: tuple[object, ...] | None = None
        self._active_speed_variation_tick_index = 0

    @property
    def device_qnh_hpa(self) -> float:
        return self._device_qnh_hpa

    @property
    def pressure_reference_qnh_hpa(self) -> float:
        return self._pressure_reference_qnh_hpa

    @property
    def seed(self) -> int:
        return self._seed

    def reseed(self, seed: int) -> None:
        self._seed = int(seed)
        self._active_directive_key = None
        self._active_variation_tick_index = 0
        self._active_speed_directive_key = None
        self._active_speed_variation_tick_index = 0

    def set_device_qnh_hpa(self, qnh_hpa: float) -> None:
        self._device_qnh_hpa = float(qnh_hpa)

    def reset(self) -> OwnshipState:
        self._elapsed_s = 0.0
        self._active_directive_key = None
        self._active_variation_tick_index = 0
        self._active_speed_directive_key = None
        self._active_speed_variation_tick_index = 0
        return self._build_state(
            latitude_deg=self._home_latitude_deg,
            longitude_deg=self._home_longitude_deg,
            gps_altitude_m=self._home_altitude_m,
            vertical_speed_ms=0.0,
            speed_kmh=0.0,
            track_deg=self._default_track_deg,
            on_ground=True,
            phase=FlightPhase.GLIDER_LAUNCH,
        )

    def step(
        self,
        state: OwnshipState,
        directive: FlightDirective,
        dt_s: float,
        *,
        wind: WindState | None = None,
    ) -> OwnshipState:
        if dt_s < 0.0:
            raise ValueError("dt_s must be >= 0.")

        speed_kmh = self._resolve_speed_kmh(directive)
        track_deg = self._resolve_track_deg(state, directive, dt_s, speed_kmh)
        vertical_speed_ms = self._resolve_vertical_speed_ms(directive)
        on_ground = bool(directive.on_ground)

        proposed_altitude_m = state.gps_altitude_m + vertical_speed_ms * dt_s
        if on_ground:
            gps_altitude_m = self._home_altitude_m
            vertical_speed_ms = 0.0
            on_ground = True
        elif proposed_altitude_m < self._home_altitude_m:
            gps_altitude_m = self._home_altitude_m
            vertical_speed_ms = 0.0
            on_ground = True
        else:
            gps_altitude_m = proposed_altitude_m
            on_ground = False

        if directive.phase == FlightPhase.STRAIGHT and directive.baro_altitude_m is not None:
            gps_altitude_m = max(self._home_altitude_m, float(directive.baro_altitude_m))
            vertical_speed_ms = 0.0
            on_ground = False

        movement_speed_kmh, movement_track_deg = self._movement_velocity(
            speed_kmh=speed_kmh,
            track_deg=track_deg,
            on_ground=on_ground,
            wind=wind,
        )

        latitude_deg, longitude_deg = advance_position(
            state.latitude_deg,
            state.longitude_deg,
            track_deg=movement_track_deg,
            speed_kmh=movement_speed_kmh,
            dt_s=dt_s,
        )

        self._elapsed_s += dt_s
        return self._build_state(
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            gps_altitude_m=gps_altitude_m,
            vertical_speed_ms=vertical_speed_ms,
            speed_kmh=speed_kmh,
            track_deg=track_deg,
            on_ground=on_ground,
            phase=directive.phase,
        )

    @staticmethod
    def _movement_velocity(
        *,
        speed_kmh: float,
        track_deg: float,
        on_ground: bool,
        wind: WindState | None,
    ) -> tuple[float, float]:
        if wind is None or on_ground:
            return speed_kmh, track_deg
        return ground_velocity_from_true_wind(
            airspeed_kmh=speed_kmh,
            track_deg=track_deg,
            wind_from_direction_deg=wind.direction_deg,
            wind_speed_kmh=wind.speed_kmh,
        )

    def apply_device_qnh_to_state(self, state: OwnshipState) -> OwnshipState:
        return replace(state, device_qnh_hpa=self._device_qnh_hpa)

    def _build_state(
        self,
        *,
        latitude_deg: float,
        longitude_deg: float,
        gps_altitude_m: float,
        vertical_speed_ms: float,
        speed_kmh: float,
        track_deg: float,
        on_ground: bool,
        phase: FlightPhase,
        baro_altitude_m: float | None = None,
    ) -> OwnshipState:
        static_pressure_hpa = static_pressure_hpa_for_altitude(
            gps_altitude_m if baro_altitude_m is None else float(baro_altitude_m),
            qnh_hpa=self._pressure_reference_qnh_hpa,
        )
        return OwnshipState(
            timestamp_utc=simulation_timestamp_utc(self._start_utc, self._elapsed_s),
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            gps_altitude_m=gps_altitude_m,
            static_pressure_hpa=static_pressure_hpa,
            device_qnh_hpa=self._device_qnh_hpa,
            vertical_speed_ms=vertical_speed_ms,
            speed_kmh=speed_kmh,
            track_deg=normalize_heading_deg(track_deg),
            on_ground=on_ground,
            phase=phase,
        )

    def _resolve_track_deg(
        self,
        state: OwnshipState,
        directive: FlightDirective,
        dt_s: float,
        speed_kmh: float,
    ) -> float:
        if directive.phase in {FlightPhase.CIRCLING_LEFT, FlightPhase.CIRCLING_RIGHT}:
            base_track_deg = state.track_deg
            if self._directive_changed(directive) and directive.target_heading_deg is not None:
                base_track_deg = normalize_heading_deg(directive.target_heading_deg)
            radius_m = directive.turn_radius_m or 110.0
            turn_direction = 1 if directive.phase == FlightPhase.CIRCLING_RIGHT else -1
            return advance_heading_deg(
                base_track_deg,
                speed_kmh=max(0.0, speed_kmh),
                turn_radius_m=radius_m,
                dt_s=dt_s,
                turn_direction=turn_direction,
            )

        if directive.target_heading_deg is not None:
            return normalize_heading_deg(directive.target_heading_deg)
        return normalize_heading_deg(state.track_deg)

    def _resolve_speed_kmh(self, directive: FlightDirective) -> float:
        if directive.on_ground:
            self._active_speed_directive_key = None
            self._active_speed_variation_tick_index = 0
            return max(0.0, float(directive.target_speed_kmh))
        if directive.phase not in {FlightPhase.CIRCLING_LEFT, FlightPhase.CIRCLING_RIGHT}:
            self._active_speed_directive_key = None
            self._active_speed_variation_tick_index = 0
            return max(0.0, float(directive.target_speed_kmh))
        if directive.speed_min_kmh is None and directive.speed_max_kmh is None:
            self._active_speed_directive_key = None
            self._active_speed_variation_tick_index = 0
            return max(0.0, float(directive.target_speed_kmh))

        key = self._speed_variation_key(directive)
        if self._active_speed_directive_key != key:
            self._active_speed_directive_key = key
            self._active_speed_variation_tick_index = 0

        minimum = float(directive.speed_min_kmh if directive.speed_min_kmh is not None else directive.target_speed_kmh)
        maximum = float(directive.speed_max_kmh if directive.speed_max_kmh is not None else directive.target_speed_kmh)
        minimum = max(0.0, minimum)
        maximum = max(0.0, maximum)
        if maximum < minimum:
            minimum, maximum = maximum, minimum

        value = self._oscillating_value_at(
            self._active_speed_variation_tick_index,
            minimum=minimum,
            maximum=maximum,
            half_cycle_ticks=DEFAULT_CIRCLING_SPEED_VARIATION_TICKS,
        )
        self._active_speed_variation_tick_index += 1
        return value

    def _resolve_vertical_speed_ms(self, directive: FlightDirective) -> float:
        key = self._variation_key(directive)
        if self._active_directive_key != key:
            self._active_directive_key = key
            self._active_variation_tick_index = 0

        if directive.on_ground:
            return 0.0

        if directive.climb_min_ms is not None or directive.climb_max_ms is not None:
            minimum = float(directive.climb_min_ms if directive.climb_min_ms is not None else directive.climb_max_ms)
            maximum = float(directive.climb_max_ms if directive.climb_max_ms is not None else directive.climb_min_ms)
            if maximum < minimum:
                minimum, maximum = maximum, minimum
            generator = SeededRangeGenerator(
                seed=self._seed,
                minimum=minimum,
                maximum=maximum,
                salt=f"{directive.segment_id}:{directive.phase.value}",
                interpolation_ticks=self._variation_interpolation_ticks(directive),
            )
            value = generator.value_at(self._active_variation_tick_index)
            self._active_variation_tick_index += 1
            return value

        if directive.sink_ms is not None:
            return float(directive.sink_ms)

        return 0.0

    def _directive_changed(self, directive: FlightDirective) -> bool:
        return self._active_directive_key != self._variation_key(directive)

    @staticmethod
    def _variation_key(directive: FlightDirective) -> tuple[object, ...]:
        return (
            directive.segment_id,
            directive.phase,
            directive.target_heading_deg,
            directive.target_speed_kmh,
            directive.baro_altitude_m,
            directive.speed_min_kmh,
            directive.speed_max_kmh,
            directive.turn_radius_m,
            directive.climb_min_ms,
            directive.climb_max_ms,
            directive.sink_ms,
            directive.on_ground,
        )

    @staticmethod
    def _speed_variation_key(directive: FlightDirective) -> tuple[object, ...]:
        return (
            directive.segment_id,
            directive.phase,
            directive.target_speed_kmh,
            directive.speed_min_kmh,
            directive.speed_max_kmh,
            directive.on_ground,
        )

    @staticmethod
    def _variation_interpolation_ticks(directive: FlightDirective) -> int:
        if directive.phase in {FlightPhase.CIRCLING_LEFT, FlightPhase.CIRCLING_RIGHT}:
            return DEFAULT_CIRCLING_VARIATION_TICKS
        if directive.phase == FlightPhase.GLIDER_LAUNCH:
            return DEFAULT_GLIDER_LAUNCH_VARIATION_TICKS
        return DEFAULT_GENERIC_VARIATION_TICKS

    @staticmethod
    def _oscillating_value_at(
        tick_index: int,
        *,
        minimum: float,
        maximum: float,
        half_cycle_ticks: int,
    ) -> float:
        if tick_index < 0:
            raise ValueError("tick_index must be >= 0.")
        if maximum == minimum:
            return minimum

        half_cycle = max(1, int(half_cycle_ticks))
        cycle_position = tick_index % (half_cycle * 2)
        if cycle_position <= half_cycle:
            blend = cycle_position / half_cycle
        else:
            blend = 1.0 - ((cycle_position - half_cycle) / half_cycle)

        eased = FlightModel._smoothstep(blend)
        return minimum + (maximum - minimum) * eased

    @staticmethod
    def _smoothstep(value: float) -> float:
        clamped = min(1.0, max(0.0, float(value)))
        return clamped * clamped * (3.0 - 2.0 * clamped)

    @staticmethod
    def _normalize_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
