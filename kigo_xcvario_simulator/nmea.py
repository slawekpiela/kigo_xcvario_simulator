"""Builders for NMEA and FLARM sentences used by the simulator."""

from __future__ import annotations

from datetime import datetime
import json
import math
from typing import Sequence

from .contracts import OwnshipState, TrafficContact, WindState
from .state import FlightPhase

DRY_AIR_GAS_CONSTANT_J_PER_KG_K = 287.05
ABSOLUTE_ZERO_C = 273.15


def nmea_checksum(sentence_body: str) -> int:
    checksum = 0
    for char in sentence_body.encode("ascii"):
        checksum ^= char
    return checksum


def build_nmea_sentence(sentence_body: str) -> str:
    checksum = nmea_checksum(sentence_body)
    return f"${sentence_body}*{checksum:02X}\r\n"


def build_gprmc(ownship: OwnshipState) -> str:
    timestamp = _parse_timestamp(ownship.timestamp_utc)
    latitude_text, latitude_hemisphere = format_latitude(ownship.latitude_deg)
    longitude_text, longitude_hemisphere = format_longitude(ownship.longitude_deg)
    speed_knots = ownship.speed_kmh / 1.852
    body = ",".join(
        [
            "GPRMC",
            timestamp.strftime("%H%M%S") + ".00",
            "A",
            latitude_text,
            latitude_hemisphere,
            longitude_text,
            longitude_hemisphere,
            f"{speed_knots:.1f}",
            f"{ownship.track_deg:.1f}",
            timestamp.strftime("%d%m%y"),
            "",
            "",
            "A",
        ]
    )
    return build_nmea_sentence(body)


def build_gpgga(ownship: OwnshipState, *, satellites: int = 8, hdop: float = 1.0) -> str:
    timestamp = _parse_timestamp(ownship.timestamp_utc)
    latitude_text, latitude_hemisphere = format_latitude(ownship.latitude_deg)
    longitude_text, longitude_hemisphere = format_longitude(ownship.longitude_deg)
    body = ",".join(
        [
            "GPGGA",
            timestamp.strftime("%H%M%S") + ".00",
            latitude_text,
            latitude_hemisphere,
            longitude_text,
            longitude_hemisphere,
            "1",
            f"{max(0, satellites):02d}",
            f"{hdop:.1f}",
            f"{ownship.gps_altitude_m:.1f}",
            "M",
            "0.0",
            "M",
            "",
            "",
        ]
    )
    return build_nmea_sentence(body)


def build_pxcv(
    ownship: OwnshipState,
    *,
    oat_c: float = 18.0,
    mac_cready_ms: float = 0.0,
    bugs_degradation_percent: int = 0,
    ballast_overload_factor: float = 1.0,
    flight_mode: int | None = None,
    dynamic_pressure_pa: float | None = None,
    valid_temperature: bool = True,
) -> str:
    resolved_flight_mode = _xcvario_flight_mode(ownship) if flight_mode is None else int(flight_mode)
    resolved_oat_c = float(oat_c) if valid_temperature else 0.0
    resolved_dynamic_pressure_pa = (
        dynamic_pressure_pa_for_speed(
            static_pressure_hpa=ownship.static_pressure_hpa,
            speed_kmh=ownship.speed_kmh,
            oat_c=resolved_oat_c,
        )
        if dynamic_pressure_pa is None
        else max(0.0, float(dynamic_pressure_pa))
    )
    body = ",".join(
        [
            "PXCV",
            f"{ownship.vertical_speed_ms:.1f}",
            f"{max(0.0, float(mac_cready_ms)):.2f}",
            str(max(0, int(bugs_degradation_percent))),
            f"{max(1.0, float(ballast_overload_factor)):.3f}",
            str(resolved_flight_mode),
            f"{resolved_oat_c:.1f}",
            f"{ownship.device_qnh_hpa:.1f}",
            f"{ownship.static_pressure_hpa:.1f}",
            f"{resolved_dynamic_pressure_pa:.1f}",
            "",
            "",
            "",
            "",
            "",
        ]
    )
    return build_nmea_sentence(body)


def build_pov(
    ownship: OwnshipState,
    *,
    oat_c: float = 18.0,
    dynamic_pressure_pa: float | None = None,
    valid_temperature: bool = True,
) -> str:
    resolved_dynamic_pressure_pa = (
        dynamic_pressure_pa_for_speed(
            static_pressure_hpa=ownship.static_pressure_hpa,
            speed_kmh=ownship.speed_kmh,
            oat_c=oat_c,
        )
        if dynamic_pressure_pa is None
        else max(0.0, float(dynamic_pressure_pa))
    )
    fields = [
        "POV",
        "P",
        f"{ownship.static_pressure_hpa:.1f}",
        "Q",
        f"{resolved_dynamic_pressure_pa:.1f}",
        "E",
        f"{ownship.vertical_speed_ms:.1f}",
    ]
    if valid_temperature:
        fields.extend(["T", f"{float(oat_c):.1f}"])
    body = ",".join(fields)
    return build_nmea_sentence(body)


def build_wimwv(wind: WindState) -> str:
    direction_deg = math.fmod(float(wind.direction_deg), 360.0)
    if direction_deg < 0.0:
        direction_deg += 360.0
    speed_kmh = max(0.0, float(wind.speed_kmh))
    body = ",".join(
        [
            "WIMWV",
            f"{direction_deg:3.1f}",
            "T",
            f"{speed_kmh:3.1f}",
            "K",
            "A",
        ]
    )
    return build_nmea_sentence(body)


def build_pflau(traffic: Sequence[TrafficContact]) -> str:
    if traffic:
        primary = min(
            traffic,
            key=lambda contact: math.hypot(contact.relative_north_m, contact.relative_east_m),
        )
        relative_distance_m = int(round(math.hypot(primary.relative_north_m, primary.relative_east_m)))
        relative_vertical_m = int(round(primary.relative_altitude_m))
        relative_bearing_deg = int(round(math.degrees(math.atan2(primary.relative_east_m, primary.relative_north_m))))
        alarm_level = max(contact.alarm_level for contact in traffic)
        identifier = primary.aircraft_id or primary.contact_id
    else:
        relative_distance_m = 0
        relative_vertical_m = 0
        relative_bearing_deg = 0
        alarm_level = 0
        identifier = ""

    body = ",".join(
        [
            "PFLAU",
            str(len(traffic)),
            "1",
            "2",
            "1",
            str(alarm_level),
            str(relative_bearing_deg),
            "0",
            str(relative_vertical_m),
            str(relative_distance_m),
            identifier,
        ]
    )
    return build_nmea_sentence(body)


def build_pflaa(contact: TrafficContact) -> str:
    identifier = contact.aircraft_id or contact.contact_id
    body = ",".join(
        [
            "PFLAA",
            str(contact.alarm_level),
            str(int(round(contact.relative_north_m))),
            str(int(round(contact.relative_east_m))),
            str(int(round(contact.relative_altitude_m))),
            "2",
            identifier,
            str(int(round(contact.track_deg))),
            "0",
            "0",
            f"{contact.climb_ms:.1f}",
            "1",
        ]
    )
    return build_nmea_sentence(body)


def format_latitude(latitude_deg: float) -> tuple[str, str]:
    return _format_coordinate(latitude_deg, degree_digits=2, positive="N", negative="S")


def format_longitude(longitude_deg: float) -> tuple[str, str]:
    return _format_coordinate(longitude_deg, degree_digits=3, positive="E", negative="W")


def snapshot_to_json_bytes(payload: object) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def dynamic_pressure_pa_for_speed(*, static_pressure_hpa: float, speed_kmh: float, oat_c: float) -> float:
    static_pressure_pa = max(0.0, float(static_pressure_hpa)) * 100.0
    temperature_k = max(1.0, float(oat_c) + ABSOLUTE_ZERO_C)
    density_kg_m3 = static_pressure_pa / (DRY_AIR_GAS_CONSTANT_J_PER_KG_K * temperature_k)
    speed_ms = max(0.0, float(speed_kmh)) / 3.6
    return 0.5 * density_kg_m3 * speed_ms * speed_ms


def _xcvario_flight_mode(ownship: OwnshipState) -> int:
    if ownship.phase in {FlightPhase.CIRCLING_LEFT, FlightPhase.CIRCLING_RIGHT}:
        return 1
    return 0


def _format_coordinate(value_deg: float, *, degree_digits: int, positive: str, negative: str) -> tuple[str, str]:
    hemisphere = positive if value_deg >= 0.0 else negative
    absolute = abs(value_deg)
    degrees = int(absolute)
    minutes = (absolute - degrees) * 60.0
    return f"{degrees:0{degree_digits}d}{minutes:06.3f}", hemisphere


def _parse_timestamp(timestamp_utc: str) -> datetime:
    return datetime.fromisoformat(str(timestamp_utc).replace("Z", "+00:00"))
