"""Scenario owner for simulator lifecycle, presets and manual mode."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import math
from threading import RLock

from .baro import qnh_hpa_for_static_pressure
from .config import HomePosition, SimulatorRuntimeConfig
from .contracts import (
    FlightDirective,
    ManualModeInput,
    PresetRequest,
    SimulationSnapshot,
    TrafficConfig,
    WindState,
)
from .flight_model import FlightModel
from .flight_math import normalize_heading_deg
from .presets import (
    DEFAULT_CIRCLING_RADIUS_M,
    DEFAULT_CIRCLING_SPEED_KMH,
    DEFAULT_CLIMB_MAX_MS,
    DEFAULT_CLIMB_MIN_MS,
    DEFAULT_GLIDER_LAUNCH_ACCELERATION_CLIMB_MAX_MS,
    DEFAULT_GLIDER_LAUNCH_ACCELERATION_CLIMB_MIN_MS,
    DEFAULT_GLIDER_LAUNCH_CLIMB_MAX_MS,
    DEFAULT_GLIDER_LAUNCH_CLIMB_MIN_MS,
    DEFAULT_GLIDER_LAUNCH_EXIT_ALTITUDE_AGL_M,
    DEFAULT_GLIDER_LAUNCH_TARGET_SPEED_KMH,
    DEFAULT_HEADING_DEG,
    DEFAULT_SINK_MS,
    DEFAULT_STRAIGHT_SPEED_KMH,
    PRESET_GLIDER_LAUNCH,
    PRESET_STRAIGHT,
    build_preset,
    build_glider_launch_sequence,
)
from .state import FlightPhase, HealthState, RuntimeState
from .traffic_database import DEFAULT_TRAFFIC_CONTACT_COUNT
from .traffic_model import (
    TrafficGenerator,
    normalize_traffic_circling_radius_range,
    normalize_traffic_motion_mode,
)


class ScenarioOrchestrator:
    """Single owner of runtime lifecycle and simulation state."""

    def __init__(
        self,
        runtime_config: SimulatorRuntimeConfig,
        *,
        flight_model: FlightModel | None = None,
        traffic_generator: TrafficGenerator | None = None,
        start_utc: datetime | None = None,
    ) -> None:
        self._lock = RLock()
        self._start_utc = self._normalize_utc(start_utc or datetime.now(timezone.utc))
        self._runtime_state = RuntimeState.STOPPED
        self._health = HealthState.READY
        self._seed = runtime_config.seed
        self._home_position = runtime_config.home_position
        self._manual_generation = 0
        self._traffic_config = TrafficConfig(enabled=True, contact_count=DEFAULT_TRAFFIC_CONTACT_COUNT)
        self._traffic = ()
        self._traffic_anchor_position: HomePosition | None = None
        self._wind = WindState()
        self._flight_model = flight_model or FlightModel(
            seed=runtime_config.seed,
            home_latitude_deg=runtime_config.home_position.latitude_deg,
            home_longitude_deg=runtime_config.home_position.longitude_deg,
            home_altitude_m=runtime_config.home_position.gps_altitude_m,
            pressure_reference_qnh_hpa=runtime_config.device_qnh_hpa,
            device_qnh_hpa=runtime_config.device_qnh_hpa,
            start_utc=self._start_utc,
        )
        self._traffic_generator = traffic_generator or TrafficGenerator(seed=runtime_config.seed)
        self._preset_plan = None
        self._preset_segment_index = 0
        self._preset_segment_elapsed_s = 0.0
        self._manual_plan = None
        self._manual_segment_index = 0
        self._manual_segment_elapsed_s = 0.0
        self._manual_directive = None
        self._sim_time_s = 0.0
        self._ownship = self._flight_model.reset()

    def start(self) -> SimulationSnapshot:
        with self._lock:
            self._runtime_state = RuntimeState.RUNNING
            return self._snapshot()

    def pause(self) -> SimulationSnapshot:
        with self._lock:
            if self._runtime_state == RuntimeState.RUNNING:
                self._runtime_state = RuntimeState.PAUSED
            return self._snapshot()

    def reset(self) -> SimulationSnapshot:
        with self._lock:
            current_state = self._runtime_state
            self._sim_time_s = 0.0
            self._preset_segment_index = 0
            self._preset_segment_elapsed_s = 0.0
            self._traffic = ()
            self._traffic_generator.reset()
            self._ownship = self._flight_model.reset()
            self._health = HealthState.READY
            self._manual_plan = None
            self._manual_segment_index = 0
            self._manual_segment_elapsed_s = 0.0
            self._manual_directive = None
            self._runtime_state = current_state
            return self._snapshot()

    def load_preset(
        self,
        request: PresetRequest,
        *,
        overrides: dict[str, object] | None = None,
    ) -> SimulationSnapshot:
        with self._lock:
            self._seed = request.seed
            self._flight_model.reseed(request.seed)
            self._traffic_generator.reseed(request.seed)
            self._preset_plan = build_preset(request.preset_id, request.seed, overrides)
            self._manual_plan = None
            self._manual_segment_index = 0
            self._manual_segment_elapsed_s = 0.0
            self._manual_directive = None
            self._preset_segment_index = 0
            self._preset_segment_elapsed_s = 0.0
            self._sim_time_s = 0.0
            self._ownship = self._flight_model.reset()
            self._ownship = self._flight_model.apply_device_qnh_to_state(self._ownship)
            self._traffic = ()
            self._runtime_state = RuntimeState.RUNNING if request.autostart else RuntimeState.STOPPED
            self._health = HealthState.READY
            return self._snapshot()

    def set_manual_mode(self, manual_input: ManualModeInput) -> SimulationSnapshot:
        with self._lock:
            self._manual_generation += 1
            self._manual_plan = None
            self._manual_segment_index = 0
            self._manual_segment_elapsed_s = 0.0
            self._manual_directive = None
            if manual_input.on_ground:
                self._sim_time_s = 0.0
                self._ownship = self._flight_model.reset()
                self._ownship = self._flight_model.apply_device_qnh_to_state(self._ownship)
                self._traffic = ()
                self._manual_directive = self._build_manual_directive(manual_input)
            elif manual_input.phase == FlightPhase.GLIDER_LAUNCH:
                self._manual_plan = self._build_manual_glider_launch_plan(manual_input)
            else:
                self._manual_directive = self._build_manual_directive(manual_input)
            self._preset_plan = None
            self._preset_segment_index = 0
            self._preset_segment_elapsed_s = 0.0
            self._apply_manual_directive_preview()
            self._health = HealthState.READY
            return self._snapshot()

    def set_home_position(
        self,
        home_position: HomePosition,
        *,
        heading_deg: float | None = None,
    ) -> SimulationSnapshot:
        with self._lock:
            self._home_position = home_position
            self._traffic_anchor_position = home_position
            self._flight_model.set_home_position(
                latitude_deg=home_position.latitude_deg,
                longitude_deg=home_position.longitude_deg,
                gps_altitude_m=home_position.gps_altitude_m,
            )
            self._sim_time_s = 0.0
            self._preset_plan = None
            self._preset_segment_index = 0
            self._preset_segment_elapsed_s = 0.0
            self._manual_plan = None
            self._manual_segment_index = 0
            self._manual_segment_elapsed_s = 0.0
            self._manual_generation += 1
            self._ownship = self._flight_model.reset()
            self._ownship = self._flight_model.apply_device_qnh_to_state(self._ownship)
            self._traffic = ()
            self._traffic_generator.reset()
            self._manual_directive = FlightDirective(
                segment_id=f"manual_{self._manual_generation}_on_ground",
                phase=FlightPhase.GLIDER_LAUNCH,
                duration_s=None,
                target_heading_deg=heading_deg if heading_deg is not None else DEFAULT_HEADING_DEG,
                target_speed_kmh=0.0,
                sink_ms=0.0,
                on_ground=True,
            )
            self._apply_manual_directive_preview()
            self._health = HealthState.READY
            return self._snapshot()

    def set_device_qnh_hpa(self, qnh_hpa: float) -> SimulationSnapshot:
        qnh_hpa = _finite_float(qnh_hpa, "qnh_hpa")
        if qnh_hpa <= 0.0:
            raise ValueError("qnh_hpa must be > 0.")
        with self._lock:
            self._flight_model.set_device_qnh_hpa(qnh_hpa)
            self._ownship = self._flight_model.apply_device_qnh_to_state(self._ownship)
            return self._snapshot()

    def set_device_altitude_m(self, altitude_m: float) -> SimulationSnapshot:
        altitude_m = _finite_float(altitude_m, "altitude_m")
        with self._lock:
            qnh_hpa = qnh_hpa_for_static_pressure(self._ownship.static_pressure_hpa, altitude_m)
            self._flight_model.set_device_qnh_hpa(qnh_hpa)
            self._ownship = self._flight_model.apply_device_qnh_to_state(self._ownship)
            return self._snapshot()

    def set_traffic_config(
        self,
        enabled: bool,
        contact_count: int,
        collision_course: bool = False,
        motion_mode: str = "orbit",
        circling_radius_min_m: float | None = None,
        circling_radius_max_m: float | None = None,
        reset_traffic: bool = False,
        traffic_anchor_position: HomePosition | None = None,
        clear_traffic_anchor: bool = False,
    ) -> SimulationSnapshot:
        if contact_count < 0:
            raise ValueError("contact_count must be >= 0.")
        circling_radius_min_m, circling_radius_max_m = normalize_traffic_circling_radius_range(
            circling_radius_min_m,
            circling_radius_max_m,
        )
        with self._lock:
            self._traffic_config = TrafficConfig(
                enabled=bool(enabled),
                contact_count=int(contact_count),
                collision_course=bool(collision_course),
                motion_mode=normalize_traffic_motion_mode(motion_mode),
                circling_radius_min_m=circling_radius_min_m,
                circling_radius_max_m=circling_radius_max_m,
            )
            anchor_changed = False
            if clear_traffic_anchor:
                anchor_changed = self._traffic_anchor_position is not None
                self._traffic_anchor_position = None
            elif traffic_anchor_position is not None:
                anchor_changed = traffic_anchor_position != self._traffic_anchor_position
                self._traffic_anchor_position = traffic_anchor_position
            if reset_traffic or anchor_changed:
                self._traffic = ()
                self._traffic_generator.reset()
            if not self._traffic_config.enabled or self._traffic_config.contact_count == 0:
                self._traffic = ()
            return self._snapshot()

    def set_wind(self, direction_deg: float, speed_kmh: float) -> SimulationSnapshot:
        direction_deg = float(direction_deg)
        speed_kmh = float(speed_kmh)
        if speed_kmh < 0.0:
            raise ValueError("speed_kmh must be >= 0.")
        with self._lock:
            self._wind = WindState(
                direction_deg=normalize_heading_deg(direction_deg),
                speed_kmh=speed_kmh,
            )
            return self._snapshot()

    def get_wind(self) -> WindState:
        with self._lock:
            return self._wind

    def get_traffic_config(self) -> TrafficConfig:
        with self._lock:
            return self._traffic_config

    def tick(self, dt_s: float) -> SimulationSnapshot:
        with self._lock:
            if dt_s < 0.0:
                raise ValueError("dt_s must be >= 0.")
            if self._runtime_state != RuntimeState.RUNNING or dt_s == 0.0:
                return self._snapshot()

            directive = self._resolve_active_directive()
            if directive is None:
                return self._snapshot()

            remaining_dt_s = dt_s
            while remaining_dt_s > 0.0 and self._runtime_state == RuntimeState.RUNNING:
                directive = self._resolve_active_directive()
                if directive is None:
                    break

                step_dt_s = remaining_dt_s
                if self._active_plan_has_timing() and directive.duration_s is not None:
                    remaining_segment_s = max(0.0, directive.duration_s - self._active_plan_elapsed_s())
                    step_dt_s = min(remaining_dt_s, remaining_segment_s)

                self._ownship = self._flight_model.step(self._ownship, directive, step_dt_s, wind=self._wind)
                self._sim_time_s += step_dt_s
                remaining_dt_s -= step_dt_s

                if self._should_transition_glider_launch_to_straight(directive):
                    self._transition_glider_launch_to_straight()
                    if remaining_dt_s <= 0.0:
                        break
                    continue

                if self._active_plan_has_timing() and directive.duration_s is not None:
                    if self._advance_active_plan(step_dt_s, directive.duration_s):
                        break

                if step_dt_s == 0.0:
                    break

            self._update_traffic(dt_s)
            return self._snapshot()

    def get_snapshot(self) -> SimulationSnapshot:
        with self._lock:
            return self._snapshot()

    def has_manual_mode(self) -> bool:
        with self._lock:
            return self._manual_directive is not None or self._manual_plan is not None

    def _update_traffic(self, dt_s: float) -> None:
        if not self._traffic_config.enabled or self._traffic_config.contact_count == 0:
            self._traffic = ()
            return

        try:
            self._traffic = self._traffic_generator.step(
                self._ownship,
                dt_s,
                anchor=self._traffic_anchor_ownship(),
                contact_count=self._traffic_config.contact_count,
                collision_course=self._traffic_config.collision_course,
                motion_mode=self._traffic_config.motion_mode,
                circling_radius_min_m=self._traffic_config.circling_radius_min_m,
                circling_radius_max_m=self._traffic_config.circling_radius_max_m,
            )
            self._health = HealthState.READY
        except Exception:
            self._traffic = ()
            self._health = HealthState.DEGRADED

    def _traffic_anchor_ownship(self):
        if self._traffic_anchor_position is None:
            return None
        return replace(
            self._ownship,
            latitude_deg=self._traffic_anchor_position.latitude_deg,
            longitude_deg=self._traffic_anchor_position.longitude_deg,
            gps_altitude_m=self._traffic_anchor_position.gps_altitude_m,
        )

    def _resolve_active_directive(self) -> FlightDirective | None:
        if self._manual_directive is not None:
            return self._manual_directive
        if self._manual_plan is not None:
            if self._manual_segment_index >= len(self._manual_plan):
                return None
            return self._manual_plan[self._manual_segment_index]
        if self._preset_plan is None:
            return None
        if self._preset_segment_index >= len(self._preset_plan.segments):
            return None
        return self._preset_plan.segments[self._preset_segment_index]

    def _apply_manual_directive_preview(self) -> None:
        directive = self._resolve_active_directive()
        if directive is None:
            return
        self._ownship = self._flight_model.preview_directive(self._ownship, directive, wind=self._wind)

    def _build_manual_directive(self, manual_input: ManualModeInput) -> FlightDirective:
        if manual_input.on_ground:
            target_heading_deg = manual_input.heading_deg
            if target_heading_deg is None:
                target_heading_deg = self._ownship.track_deg if self._ownship.track_deg is not None else DEFAULT_HEADING_DEG
            return FlightDirective(
                segment_id=f"manual_{self._manual_generation}_on_ground",
                phase=FlightPhase.GLIDER_LAUNCH,
                duration_s=None,
                target_heading_deg=target_heading_deg,
                target_speed_kmh=0.0,
                sink_ms=0.0,
                on_ground=True,
            )

        speed_kmh = manual_input.speed_kmh
        if speed_kmh is None:
            speed_kmh = DEFAULT_CIRCLING_SPEED_KMH if manual_input.phase in {
                FlightPhase.CIRCLING_LEFT,
                FlightPhase.CIRCLING_RIGHT,
            } else DEFAULT_STRAIGHT_SPEED_KMH

        target_heading_deg = manual_input.heading_deg
        if target_heading_deg is None and manual_input.phase not in {
            FlightPhase.CIRCLING_LEFT,
            FlightPhase.CIRCLING_RIGHT,
        }:
            target_heading_deg = self._ownship.track_deg if self._ownship.track_deg is not None else DEFAULT_HEADING_DEG

        climb_min_ms = manual_input.climb_min_ms
        climb_max_ms = manual_input.climb_max_ms
        if manual_input.phase in {FlightPhase.CIRCLING_LEFT, FlightPhase.CIRCLING_RIGHT}:
            if climb_min_ms is None:
                climb_min_ms = DEFAULT_CLIMB_MIN_MS
            if climb_max_ms is None:
                climb_max_ms = DEFAULT_CLIMB_MAX_MS

        sink_ms = manual_input.sink_ms
        if manual_input.phase == FlightPhase.SINK and sink_ms is None:
            sink_ms = DEFAULT_SINK_MS

        return FlightDirective(
            segment_id=f"manual_{self._manual_generation}",
            phase=manual_input.phase,
            duration_s=None,
            target_heading_deg=target_heading_deg,
            target_speed_kmh=float(speed_kmh),
            baro_altitude_m=manual_input.baro_altitude_m
            if manual_input.phase == FlightPhase.STRAIGHT
            else None,
            speed_min_kmh=manual_input.speed_min_kmh
            if manual_input.phase in {FlightPhase.CIRCLING_LEFT, FlightPhase.CIRCLING_RIGHT}
            else None,
            speed_max_kmh=manual_input.speed_max_kmh
            if manual_input.phase in {FlightPhase.CIRCLING_LEFT, FlightPhase.CIRCLING_RIGHT}
            else None,
            turn_radius_m=float(manual_input.turn_radius_m or DEFAULT_CIRCLING_RADIUS_M)
            if manual_input.phase in {FlightPhase.CIRCLING_LEFT, FlightPhase.CIRCLING_RIGHT}
            else None,
            climb_min_ms=climb_min_ms,
            climb_max_ms=climb_max_ms,
            sink_ms=sink_ms,
            on_ground=False,
        )

    def _build_manual_glider_launch_plan(self, manual_input: ManualModeInput) -> tuple[FlightDirective, ...]:
        target_heading_deg = manual_input.heading_deg
        if target_heading_deg is None:
            target_heading_deg = self._ownship.track_deg if self._ownship.track_deg is not None else DEFAULT_HEADING_DEG

        target_speed_kmh = (
            float(manual_input.speed_kmh)
            if manual_input.speed_kmh is not None
            else DEFAULT_GLIDER_LAUNCH_TARGET_SPEED_KMH
        )
        climb_min_ms = (
            manual_input.climb_min_ms
            if manual_input.climb_min_ms is not None
            else DEFAULT_GLIDER_LAUNCH_CLIMB_MIN_MS
        )
        climb_max_ms = (
            manual_input.climb_max_ms
            if manual_input.climb_max_ms is not None
            else DEFAULT_GLIDER_LAUNCH_CLIMB_MAX_MS
        )
        acceleration_climb_min_ms = (
            manual_input.climb_min_ms
            if manual_input.climb_min_ms is not None
            else DEFAULT_GLIDER_LAUNCH_ACCELERATION_CLIMB_MIN_MS
        )
        acceleration_climb_max_ms = (
            manual_input.climb_max_ms
            if manual_input.climb_max_ms is not None
            else DEFAULT_GLIDER_LAUNCH_ACCELERATION_CLIMB_MAX_MS
        )
        return build_glider_launch_sequence(
            heading_deg=float(target_heading_deg),
            target_speed_kmh=target_speed_kmh,
            climb_min_ms=climb_min_ms,
            climb_max_ms=climb_max_ms,
            acceleration_climb_min_ms=acceleration_climb_min_ms,
            acceleration_climb_max_ms=acceleration_climb_max_ms,
            post_acceleration_duration_s=None,
        )

    def _should_transition_glider_launch_to_straight(self, directive: FlightDirective) -> bool:
        if directive.phase != FlightPhase.GLIDER_LAUNCH or self._ownship.on_ground:
            return False

        if self._manual_plan is None:
            if self._preset_plan is None or self._preset_plan.preset_id != PRESET_GLIDER_LAUNCH:
                return False

        return self._ownship.gps_altitude_m >= self._glider_launch_exit_altitude_m()

    def _transition_glider_launch_to_straight(self) -> None:
        heading_deg = float(self._ownship.track_deg if self._ownship.track_deg is not None else DEFAULT_HEADING_DEG)
        speed_kmh = float(self._ownship.speed_kmh if self._ownship.speed_kmh > 0.0 else DEFAULT_STRAIGHT_SPEED_KMH)
        self._ownship = replace(
            self._ownship,
            phase=FlightPhase.STRAIGHT,
            vertical_speed_ms=0.0,
        )

        if self._manual_plan is not None:
            self._manual_generation += 1
            self._manual_plan = None
            self._manual_segment_index = 0
            self._manual_segment_elapsed_s = 0.0
            self._manual_directive = FlightDirective(
                segment_id=f"manual_{self._manual_generation}_straight_exit",
                phase=FlightPhase.STRAIGHT,
                duration_s=None,
                target_heading_deg=heading_deg,
                target_speed_kmh=speed_kmh,
            )
            return

        self._preset_plan = build_preset(
            PRESET_STRAIGHT,
            self._seed,
            overrides={
                "heading_deg": heading_deg,
                "speed_kmh": speed_kmh,
            },
        )
        self._preset_segment_index = 0
        self._preset_segment_elapsed_s = 0.0

    def _glider_launch_exit_altitude_m(self) -> float:
        return self._home_position.gps_altitude_m + DEFAULT_GLIDER_LAUNCH_EXIT_ALTITUDE_AGL_M

    def _active_plan_has_timing(self) -> bool:
        return self._manual_plan is not None or self._preset_plan is not None

    def _active_plan_elapsed_s(self) -> float:
        if self._manual_plan is not None:
            return self._manual_segment_elapsed_s
        return self._preset_segment_elapsed_s

    def _advance_active_plan(self, step_dt_s: float, segment_duration_s: float) -> bool:
        if self._manual_plan is not None:
            self._manual_segment_elapsed_s += step_dt_s
            if self._manual_segment_elapsed_s >= segment_duration_s - 1e-9:
                self._manual_segment_index += 1
                self._manual_segment_elapsed_s = 0.0
            return False

        self._preset_segment_elapsed_s += step_dt_s
        if self._preset_segment_elapsed_s >= segment_duration_s - 1e-9:
            self._preset_segment_index += 1
            self._preset_segment_elapsed_s = 0.0
            if self._preset_plan is not None and self._preset_segment_index >= len(self._preset_plan.segments):
                self._runtime_state = RuntimeState.STOPPED
                return True
        return False

    def _snapshot(self) -> SimulationSnapshot:
        return SimulationSnapshot(
            runtime_state=self._runtime_state,
            ownship=self._ownship,
            traffic=tuple(self._traffic),
            wind=self._wind,
            preset_id=self._preset_plan.preset_id if self._preset_plan is not None else None,
            seed=self._seed,
            sim_time_s=self._sim_time_s,
            health=self._health,
        )

    @staticmethod
    def _normalize_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def _finite_float(value: float, field_name: str) -> float:
    resolved = float(value)
    if not math.isfinite(resolved):
        raise ValueError(f"{field_name} must be finite.")
    return resolved
