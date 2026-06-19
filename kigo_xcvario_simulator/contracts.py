"""Dataclasses used across simulator runtime and tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import FlightPhase, HealthState, RuntimeState

TRAFFIC_MOTION_ORBIT = "orbit"
TRAFFIC_MOTION_STRAIGHT = "straight"
TRAFFIC_MOTION_MODES = frozenset((TRAFFIC_MOTION_ORBIT, TRAFFIC_MOTION_STRAIGHT))
TRAFFIC_CIRCLING_RADIUS_MIN_M = 100.0
TRAFFIC_CIRCLING_RADIUS_MAX_M = 700.0


@dataclass(frozen=True)
class ManualModeInput:
    phase: FlightPhase
    heading_deg: float | None = None
    speed_kmh: float | None = None
    baro_altitude_m: float | None = None
    speed_min_kmh: float | None = None
    speed_max_kmh: float | None = None
    turn_radius_m: float | None = None
    climb_min_ms: float | None = None
    climb_max_ms: float | None = None
    sink_ms: float | None = None
    on_ground: bool = False


@dataclass(frozen=True)
class OwnshipState:
    timestamp_utc: str
    latitude_deg: float
    longitude_deg: float
    gps_altitude_m: float
    static_pressure_hpa: float
    device_qnh_hpa: float
    vertical_speed_ms: float
    speed_kmh: float
    track_deg: float
    on_ground: bool
    phase: FlightPhase
    device_altitude_m: float | None = None


@dataclass(frozen=True)
class TrafficContact:
    contact_id: str
    relative_north_m: float
    relative_east_m: float
    relative_altitude_m: float
    track_deg: float
    climb_ms: float
    alarm_level: int = 0
    speed_ms: float = 0.0
    aircraft_id: str = ""
    competition_id: str = ""
    registration: str = ""
    aircraft_model: str = ""


@dataclass(frozen=True)
class TrafficConfig:
    enabled: bool = True
    contact_count: int = 0
    collision_course: bool = False
    motion_mode: str = TRAFFIC_MOTION_ORBIT
    circling_radius_min_m: float = TRAFFIC_CIRCLING_RADIUS_MIN_M
    circling_radius_max_m: float = TRAFFIC_CIRCLING_RADIUS_MAX_M


@dataclass(frozen=True)
class WindState:
    direction_deg: float = 0.0
    speed_kmh: float = 0.0


@dataclass(frozen=True)
class FlightDirective:
    segment_id: str
    phase: FlightPhase
    duration_s: float | None
    target_heading_deg: float | None
    target_speed_kmh: float
    baro_altitude_m: float | None = None
    speed_min_kmh: float | None = None
    speed_max_kmh: float | None = None
    turn_radius_m: float | None = None
    climb_min_ms: float | None = None
    climb_max_ms: float | None = None
    sink_ms: float | None = None
    on_ground: bool = False


@dataclass(frozen=True)
class PresetPlan:
    preset_id: str
    seed: int
    segments: tuple[FlightDirective, ...]
    description: str = ""


@dataclass(frozen=True)
class PresetRequest:
    preset_id: str
    seed: int
    autostart: bool = True


@dataclass(frozen=True)
class SimulationSnapshot:
    runtime_state: RuntimeState
    ownship: OwnshipState
    traffic: tuple[TrafficContact, ...] = field(default_factory=tuple)
    preset_id: str | None = None
    seed: int = 0
    sim_time_s: float = 0.0
    health: HealthState = HealthState.STARTING
    wind: WindState = field(default_factory=WindState)
