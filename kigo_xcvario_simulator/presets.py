"""Preset library for the simulator MVP."""

from __future__ import annotations

from typing import Mapping

from .contracts import FlightDirective, PresetPlan
from .state import FlightPhase


PRESET_GLIDER_LAUNCH = "glider_launch"
PRESET_ON_GROUND = "on_ground"
PRESET_CIRCLING = "circling"
PRESET_STRAIGHT = "straight"
PRESET_GLIDER_LANDING = "glider_landing"
PRESET_FULL_FLIGHT = "full_flight"

DEFAULT_HEADING_DEG = 90.0
DEFAULT_GLIDER_LAUNCH_TARGET_SPEED_KMH = 100.0
DEFAULT_GLIDER_LAUNCH_EXIT_ALTITUDE_AGL_M = 150.0
DEFAULT_GLIDER_LAUNCH_GROUND_HOLD_S = 3.0
DEFAULT_GLIDER_LAUNCH_ACCELERATION_S = 15.0
DEFAULT_GLIDER_LAUNCH_ACCELERATION_STEP_S = 0.1
DEFAULT_GLIDER_LAUNCH_NO_CLIMB_S = 15.0
DEFAULT_GLIDER_LAUNCH_LOW_CLIMB_S = 5.0
DEFAULT_GLIDER_LAUNCH_LOW_CLIMB_MIN_MS = 1.0
DEFAULT_GLIDER_LAUNCH_LOW_CLIMB_MAX_MS = 1.0
DEFAULT_GLIDER_LAUNCH_ACCELERATION_CLIMB_MIN_MS = DEFAULT_GLIDER_LAUNCH_LOW_CLIMB_MIN_MS
DEFAULT_GLIDER_LAUNCH_ACCELERATION_CLIMB_MAX_MS = DEFAULT_GLIDER_LAUNCH_LOW_CLIMB_MAX_MS
DEFAULT_GLIDER_LAUNCH_CLIMB_MIN_MS = 4.0
DEFAULT_GLIDER_LAUNCH_CLIMB_MAX_MS = 4.0
DEFAULT_GLIDER_LAUNCH_POST_ACCELERATION_S = (
    DEFAULT_GLIDER_LAUNCH_EXIT_ALTITUDE_AGL_M
    - DEFAULT_GLIDER_LAUNCH_LOW_CLIMB_S * DEFAULT_GLIDER_LAUNCH_LOW_CLIMB_MIN_MS
) / DEFAULT_GLIDER_LAUNCH_CLIMB_MIN_MS
DEFAULT_STRAIGHT_SPEED_KMH = 92.0
DEFAULT_CIRCLING_SPEED_KMH = 78.0
DEFAULT_CIRCLING_RADIUS_M = 110.0
DEFAULT_CLIMB_MIN_MS = 2.0
DEFAULT_CLIMB_MAX_MS = 3.0
DEFAULT_SINK_MS = -2.0
DEFAULT_CIRCLING_SPEED_VARIATION_KMH = 2.0


def build_preset(
    preset_id: str,
    seed: int,
    overrides: Mapping[str, object] | None = None,
) -> PresetPlan:
    builder = _PRESET_BUILDERS.get(preset_id)
    if builder is None:
        known = ", ".join(sorted(_PRESET_BUILDERS))
        raise ValueError(f"Unknown preset_id {preset_id!r}. Expected one of: {known}.")
    normalized = dict(overrides or {})
    return PresetPlan(
        preset_id=preset_id,
        seed=int(seed),
        segments=builder(normalized),
        description=_PRESET_DESCRIPTIONS[preset_id],
    )


def available_preset_ids() -> tuple[str, ...]:
    return tuple(_PRESET_BUILDERS)


def _build_glider_launch(overrides: Mapping[str, object]) -> tuple[FlightDirective, ...]:
    return build_glider_launch_sequence(
        **_build_glider_launch_kwargs(overrides),
        post_acceleration_duration_s=None,
    )


def _build_on_ground(overrides: Mapping[str, object]) -> tuple[FlightDirective, ...]:
    return (
        FlightDirective(
            segment_id="on_ground",
            phase=FlightPhase.GLIDER_LAUNCH,
            duration_s=None,
            target_heading_deg=_float_override(overrides, "heading_deg", DEFAULT_HEADING_DEG),
            target_speed_kmh=0.0,
            sink_ms=0.0,
            on_ground=True,
        ),
    )


def _build_circling(overrides: Mapping[str, object]) -> tuple[FlightDirective, ...]:
    direction = str(overrides.get("direction", "left")).strip().lower()
    phase = FlightPhase.CIRCLING_RIGHT if direction == "right" else FlightPhase.CIRCLING_LEFT
    target_speed_kmh = _float_override(overrides, "speed_kmh", DEFAULT_CIRCLING_SPEED_KMH)
    speed_min_kmh, speed_max_kmh = _ordered_range(
        _float_override(
            overrides,
            "speed_min_kmh",
            target_speed_kmh - DEFAULT_CIRCLING_SPEED_VARIATION_KMH,
        ),
        _float_override(
            overrides,
            "speed_max_kmh",
            target_speed_kmh + DEFAULT_CIRCLING_SPEED_VARIATION_KMH,
        ),
    )
    return (
        FlightDirective(
            segment_id="circling_core",
            phase=phase,
            duration_s=_float_override(overrides, "duration_s", 180.0),
            target_heading_deg=_optional_float_override(overrides, "heading_deg"),
            target_speed_kmh=target_speed_kmh,
            speed_min_kmh=speed_min_kmh,
            speed_max_kmh=speed_max_kmh,
            turn_radius_m=_float_override(overrides, "turn_radius_m", DEFAULT_CIRCLING_RADIUS_M),
            climb_min_ms=_float_override(overrides, "climb_min_ms", DEFAULT_CLIMB_MIN_MS),
            climb_max_ms=_float_override(overrides, "climb_max_ms", DEFAULT_CLIMB_MAX_MS),
        ),
    )


def _build_straight(overrides: Mapping[str, object]) -> tuple[FlightDirective, ...]:
    return (
        FlightDirective(
            segment_id="straight_leg",
            phase=FlightPhase.STRAIGHT,
            duration_s=_float_override(overrides, "duration_s", 240.0),
            target_heading_deg=_float_override(overrides, "heading_deg", DEFAULT_HEADING_DEG),
            target_speed_kmh=_float_override(overrides, "speed_kmh", DEFAULT_STRAIGHT_SPEED_KMH),
        ),
    )


def _build_glider_landing(overrides: Mapping[str, object]) -> tuple[FlightDirective, ...]:
    heading_deg = _float_override(overrides, "heading_deg", DEFAULT_HEADING_DEG)
    return (
        FlightDirective(
            segment_id="approach",
            phase=FlightPhase.GLIDER_LANDING,
            duration_s=30.0,
            target_heading_deg=heading_deg,
            target_speed_kmh=78.0,
            sink_ms=_float_override(overrides, "sink_ms", -1.8),
        ),
        FlightDirective(
            segment_id="flare",
            phase=FlightPhase.GLIDER_LANDING,
            duration_s=8.0,
            target_heading_deg=heading_deg,
            target_speed_kmh=58.0,
            sink_ms=-0.6,
        ),
        FlightDirective(
            segment_id="rollout",
            phase=FlightPhase.GLIDER_LANDING,
            duration_s=12.0,
            target_heading_deg=heading_deg,
            target_speed_kmh=24.0,
            sink_ms=0.0,
            on_ground=True,
        ),
    )


def _build_full_flight(overrides: Mapping[str, object]) -> tuple[FlightDirective, ...]:
    circling_direction = str(overrides.get("circling_direction", "left")).strip().lower()
    return (
        *build_glider_launch_sequence(
            **_build_glider_launch_kwargs(overrides),
            post_acceleration_duration_s=_float_override(
                overrides,
                "launch_post_acceleration_duration_s",
                DEFAULT_GLIDER_LAUNCH_POST_ACCELERATION_S,
            ),
        ),
        *_build_circling({**overrides, "direction": circling_direction}),
        *_build_straight(overrides),
        *_build_glider_landing(overrides),
    )


def _float_override(overrides: Mapping[str, object], key: str, default: float) -> float:
    value = overrides.get(key)
    return default if value is None else float(value)


def _optional_float_override(overrides: Mapping[str, object], key: str) -> float | None:
    value = overrides.get(key)
    return None if value is None else float(value)


def _float_override_any(overrides: Mapping[str, object], keys: tuple[str, ...], default: float) -> float:
    for key in keys:
        value = overrides.get(key)
        if value is not None:
            return float(value)
    return default


def _ordered_range(first: float, second: float) -> tuple[float, float]:
    lower = max(0.0, float(first))
    upper = max(0.0, float(second))
    return (lower, upper) if lower <= upper else (upper, lower)


def _build_glider_launch_kwargs(overrides: Mapping[str, object]) -> dict[str, float]:
    return {
        "heading_deg": _float_override(overrides, "heading_deg", DEFAULT_HEADING_DEG),
        "target_speed_kmh": _float_override(overrides, "speed_kmh", DEFAULT_GLIDER_LAUNCH_TARGET_SPEED_KMH),
        "climb_min_ms": _float_override(
            overrides,
            "climb_min_ms",
            DEFAULT_GLIDER_LAUNCH_CLIMB_MIN_MS,
        ),
        "climb_max_ms": _float_override(
            overrides,
            "climb_max_ms",
            DEFAULT_GLIDER_LAUNCH_CLIMB_MAX_MS,
        ),
        "acceleration_climb_min_ms": _float_override_any(
            overrides,
            ("launch_low_climb_min_ms", "launch_acceleration_climb_min_ms"),
            DEFAULT_GLIDER_LAUNCH_ACCELERATION_CLIMB_MIN_MS,
        ),
        "acceleration_climb_max_ms": _float_override_any(
            overrides,
            ("launch_low_climb_max_ms", "launch_acceleration_climb_max_ms"),
            DEFAULT_GLIDER_LAUNCH_ACCELERATION_CLIMB_MAX_MS,
        ),
    }


def build_glider_launch_sequence(
    *,
    heading_deg: float,
    target_speed_kmh: float,
    climb_min_ms: float | None,
    climb_max_ms: float | None,
    acceleration_climb_min_ms: float | None = None,
    acceleration_climb_max_ms: float | None = None,
    post_acceleration_duration_s: float | None = DEFAULT_GLIDER_LAUNCH_POST_ACCELERATION_S,
) -> tuple[FlightDirective, ...]:
    low_climb_min_ms = (
        DEFAULT_GLIDER_LAUNCH_LOW_CLIMB_MIN_MS
        if acceleration_climb_min_ms is None
        else acceleration_climb_min_ms
    )
    low_climb_max_ms = (
        DEFAULT_GLIDER_LAUNCH_LOW_CLIMB_MAX_MS
        if acceleration_climb_max_ms is None
        else acceleration_climb_max_ms
    )
    segments: list[FlightDirective] = [
        FlightDirective(
            segment_id="ground_hold",
            phase=FlightPhase.GLIDER_LAUNCH,
            duration_s=DEFAULT_GLIDER_LAUNCH_GROUND_HOLD_S,
            target_heading_deg=heading_deg,
            target_speed_kmh=0.0,
            sink_ms=0.0,
            on_ground=True,
        )
    ]

    acceleration_step_count = int(
        round(DEFAULT_GLIDER_LAUNCH_ACCELERATION_S / DEFAULT_GLIDER_LAUNCH_ACCELERATION_STEP_S)
    )
    for step_index in range(acceleration_step_count):
        elapsed_at_step_start_s = (
            DEFAULT_GLIDER_LAUNCH_GROUND_HOLD_S
            + float(step_index) * DEFAULT_GLIDER_LAUNCH_ACCELERATION_STEP_S
        )
        climb_range = _glider_launch_climb_range_for_elapsed_s(
            elapsed_at_step_start_s,
            low_climb_min_ms=low_climb_min_ms,
            low_climb_max_ms=low_climb_max_ms,
            climb_min_ms=climb_min_ms,
            climb_max_ms=climb_max_ms,
        )
        segments.append(
            FlightDirective(
                segment_id=f"launch_accel_{step_index + 1:03d}",
                phase=FlightPhase.GLIDER_LAUNCH,
                duration_s=DEFAULT_GLIDER_LAUNCH_ACCELERATION_STEP_S,
                target_heading_deg=heading_deg,
                target_speed_kmh=float(target_speed_kmh) * float(step_index + 1) / float(acceleration_step_count),
                climb_min_ms=climb_range[0],
                climb_max_ms=climb_range[1],
            )
        )

    elapsed_after_acceleration_s = DEFAULT_GLIDER_LAUNCH_GROUND_HOLD_S + DEFAULT_GLIDER_LAUNCH_ACCELERATION_S
    low_climb_end_s = DEFAULT_GLIDER_LAUNCH_NO_CLIMB_S + DEFAULT_GLIDER_LAUNCH_LOW_CLIMB_S
    if elapsed_after_acceleration_s < DEFAULT_GLIDER_LAUNCH_NO_CLIMB_S:
        segments.append(
            FlightDirective(
                segment_id="launch_no_climb",
                phase=FlightPhase.GLIDER_LAUNCH,
                duration_s=DEFAULT_GLIDER_LAUNCH_NO_CLIMB_S - elapsed_after_acceleration_s,
                target_heading_deg=heading_deg,
                target_speed_kmh=float(target_speed_kmh),
                climb_min_ms=0.0,
                climb_max_ms=0.0,
            )
        )
        elapsed_after_acceleration_s = DEFAULT_GLIDER_LAUNCH_NO_CLIMB_S

    if elapsed_after_acceleration_s < low_climb_end_s:
        segments.append(
            FlightDirective(
                segment_id="launch_climb_1ms",
                phase=FlightPhase.GLIDER_LAUNCH,
                duration_s=low_climb_end_s - elapsed_after_acceleration_s,
                target_heading_deg=heading_deg,
                target_speed_kmh=float(target_speed_kmh),
                climb_min_ms=low_climb_min_ms,
                climb_max_ms=low_climb_max_ms,
            )
        )

    segments.append(
        FlightDirective(
            segment_id="initial_climb",
            phase=FlightPhase.GLIDER_LAUNCH,
            duration_s=post_acceleration_duration_s,
            target_heading_deg=heading_deg,
            target_speed_kmh=float(target_speed_kmh),
            climb_min_ms=climb_min_ms,
            climb_max_ms=climb_max_ms,
        )
    )
    return tuple(segments)


def _glider_launch_climb_range_for_elapsed_s(
    elapsed_s: float,
    *,
    low_climb_min_ms: float | None,
    low_climb_max_ms: float | None,
    climb_min_ms: float | None,
    climb_max_ms: float | None,
) -> tuple[float | None, float | None]:
    low_climb_end_s = DEFAULT_GLIDER_LAUNCH_NO_CLIMB_S + DEFAULT_GLIDER_LAUNCH_LOW_CLIMB_S
    if elapsed_s < DEFAULT_GLIDER_LAUNCH_NO_CLIMB_S:
        return 0.0, 0.0
    if elapsed_s < low_climb_end_s:
        return low_climb_min_ms, low_climb_max_ms
    return climb_min_ms, climb_max_ms


_PRESET_BUILDERS = {
    PRESET_ON_GROUND: _build_on_ground,
    PRESET_GLIDER_LAUNCH: _build_glider_launch,
    PRESET_CIRCLING: _build_circling,
    PRESET_STRAIGHT: _build_straight,
    PRESET_GLIDER_LANDING: _build_glider_landing,
    PRESET_FULL_FLIGHT: _build_full_flight,
}

_PRESET_DESCRIPTIONS = {
    PRESET_ON_GROUND: "Stationary glider on the ground.",
    PRESET_GLIDER_LAUNCH: "Ground roll, liftoff and initial glider climb.",
    PRESET_CIRCLING: "Circling in a thermal with deterministic climb range.",
    PRESET_STRAIGHT: "Stable straight flight on a commanded heading.",
    PRESET_GLIDER_LANDING: "Approach, flare and rollout for a glider landing.",
    PRESET_FULL_FLIGHT: "Launch, circling, straight cruise and glider landing.",
}
