"""Pure helpers for simulator flight kinematics."""

from __future__ import annotations

import math


EARTH_RADIUS_M = 6_371_000.0
KMH_TO_MS = 1000.0 / 3600.0


def normalize_heading_deg(heading_deg: float) -> float:
    normalized = math.fmod(heading_deg, 360.0)
    if normalized < 0.0:
        normalized += 360.0
    return normalized


def speed_kmh_to_ms(speed_kmh: float) -> float:
    return speed_kmh * KMH_TO_MS


def travel_distance_m(speed_kmh: float, dt_s: float) -> float:
    return speed_kmh_to_ms(speed_kmh) * dt_s


def calculate_turn_rate_deg_s(speed_kmh: float, turn_radius_m: float) -> float:
    if turn_radius_m <= 0.0:
        raise ValueError("turn_radius_m must be positive.")
    speed_ms = speed_kmh_to_ms(speed_kmh)
    if speed_ms < 0.0:
        raise ValueError("speed_kmh must be non-negative.")
    angular_rate_rad_s = speed_ms / turn_radius_m
    return math.degrees(angular_rate_rad_s)


def calculate_turn_radius_m(speed_kmh: float, turn_rate_deg_s: float) -> float:
    rate_rad_s = math.radians(turn_rate_deg_s)
    if rate_rad_s <= 0.0:
        raise ValueError("turn_rate_deg_s must be positive.")
    return speed_kmh_to_ms(speed_kmh) / rate_rad_s


def advance_heading_deg(
    current_heading_deg: float,
    *,
    speed_kmh: float,
    turn_radius_m: float,
    dt_s: float,
    turn_direction: int,
) -> float:
    if turn_direction not in {-1, 1}:
        raise ValueError("turn_direction must be -1 for left or 1 for right.")
    delta_deg = calculate_turn_rate_deg_s(speed_kmh, turn_radius_m) * dt_s * turn_direction
    return normalize_heading_deg(current_heading_deg + delta_deg)


def advance_position(
    latitude_deg: float,
    longitude_deg: float,
    *,
    track_deg: float,
    speed_kmh: float,
    dt_s: float,
) -> tuple[float, float]:
    distance_m = travel_distance_m(speed_kmh, dt_s)
    if distance_m == 0.0:
        return latitude_deg, longitude_deg

    track_rad = math.radians(normalize_heading_deg(track_deg))
    latitude_rad = math.radians(latitude_deg)
    longitude_rad = math.radians(longitude_deg)
    angular_distance = distance_m / EARTH_RADIUS_M

    new_latitude_rad = math.asin(
        math.sin(latitude_rad) * math.cos(angular_distance)
        + math.cos(latitude_rad) * math.sin(angular_distance) * math.cos(track_rad)
    )
    new_longitude_rad = longitude_rad + math.atan2(
        math.sin(track_rad) * math.sin(angular_distance) * math.cos(latitude_rad),
        math.cos(angular_distance) - math.sin(latitude_rad) * math.sin(new_latitude_rad),
    )

    return math.degrees(new_latitude_rad), normalize_longitude_deg(math.degrees(new_longitude_rad))


def bearing_between_points_deg(
    latitude_a_deg: float,
    longitude_a_deg: float,
    latitude_b_deg: float,
    longitude_b_deg: float,
) -> float:
    latitude_a_rad = math.radians(latitude_a_deg)
    latitude_b_rad = math.radians(latitude_b_deg)
    delta_longitude_rad = math.radians(longitude_b_deg - longitude_a_deg)

    x = math.sin(delta_longitude_rad) * math.cos(latitude_b_rad)
    y = (
        math.cos(latitude_a_rad) * math.sin(latitude_b_rad)
        - math.sin(latitude_a_rad) * math.cos(latitude_b_rad) * math.cos(delta_longitude_rad)
    )
    return normalize_heading_deg(math.degrees(math.atan2(x, y)))


def normalize_longitude_deg(longitude_deg: float) -> float:
    normalized = math.fmod(longitude_deg + 180.0, 360.0)
    if normalized < 0.0:
        normalized += 360.0
    return normalized - 180.0
