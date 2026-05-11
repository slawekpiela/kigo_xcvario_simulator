"""Barometric helpers shared by simulator modules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math


STANDARD_QNH_HPA = 1013.25
BARO_K1 = 0.190263
BARO_K2 = 8.417286e-5


def qnh_altitude_to_static_pressure_hpa(qnh_hpa: float, altitude_m: float) -> float:
    base = math.pow(float(qnh_hpa), BARO_K1) - BARO_K2 * float(altitude_m)
    if base <= 0:
        raise ValueError("Invalid QNH/altitude combination for pressure conversion.")
    return math.pow(base, 1.0 / BARO_K1)


def static_pressure_to_qnh_altitude_m(qnh_hpa: float, static_pressure_hpa: float) -> float:
    return (math.pow(float(qnh_hpa), BARO_K1) - math.pow(float(static_pressure_hpa), BARO_K1)) / BARO_K2


def find_qnh_from_pressure_hpa(static_pressure_hpa: float, altitude_m: float) -> float:
    return qnh_altitude_to_static_pressure_hpa(float(static_pressure_hpa), -float(altitude_m))


def static_pressure_hpa_for_altitude(altitude_m: float, *, qnh_hpa: float = STANDARD_QNH_HPA) -> float:
    return qnh_altitude_to_static_pressure_hpa(qnh_hpa, altitude_m)


def altitude_m_for_static_pressure(static_pressure_hpa: float, *, qnh_hpa: float = STANDARD_QNH_HPA) -> float:
    return static_pressure_to_qnh_altitude_m(qnh_hpa, static_pressure_hpa)


def qnh_hpa_for_static_pressure(static_pressure_hpa: float, altitude_m: float) -> float:
    return find_qnh_from_pressure_hpa(static_pressure_hpa, altitude_m)


def simulation_timestamp_utc(start_utc: datetime, sim_time_s: float) -> str:
    anchor = _normalize_utc_datetime(start_utc)
    point = anchor + timedelta(seconds=sim_time_s)
    return point.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
