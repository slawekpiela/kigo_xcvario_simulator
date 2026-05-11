"""Small XCvario stream parser used by simulator compatibility tests."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Protocol

from .baro import STANDARD_QNH_HPA, qnh_altitude_to_static_pressure_hpa, static_pressure_to_qnh_altitude_m


DEFAULT_READ_TIMEOUT_S = 0.5


@dataclass(frozen=True)
class XCVarioPressureSample:
    static_pressure_hpa: float
    device_qnh_hpa: float | None
    altitude_m: float | None
    protocol: str
    raw_sentence: str
    latitude_deg: float | None = None
    longitude_deg: float | None = None


class ByteTransport(Protocol):
    def read(self, size: int, timeout_s: float) -> bytes:
        ...

    def write(self, data: bytes, timeout_s: float) -> None:
        ...

    def close(self) -> None:
        ...


def read_next_pressure_sample(
    transport: ByteTransport,
    *,
    timeout_s: float = 1.5,
    initial_buffer: bytes = b"",
) -> tuple[XCVarioPressureSample | None, bytes]:
    deadline = time.monotonic() + max(timeout_s, 0.05)
    buffer = bytearray(initial_buffer)
    latest_latitude_deg: float | None = None
    latest_longitude_deg: float | None = None

    while time.monotonic() < deadline:
        while b"\n" in buffer:
            raw_line, _, remainder = bytes(buffer).partition(b"\n")
            buffer = bytearray(remainder)
            sentence = raw_line.strip().decode("ascii", errors="ignore")
            gps_position = _parse_gps_sentence(sentence)
            if gps_position is not None:
                latest_latitude_deg, latest_longitude_deg = gps_position
                continue
            sample = parse_pressure_sentence(sentence)
            if sample is not None:
                if latest_latitude_deg is not None and latest_longitude_deg is not None:
                    sample = XCVarioPressureSample(
                        static_pressure_hpa=sample.static_pressure_hpa,
                        device_qnh_hpa=sample.device_qnh_hpa,
                        altitude_m=sample.altitude_m,
                        protocol=sample.protocol,
                        raw_sentence=sample.raw_sentence,
                        latitude_deg=latest_latitude_deg,
                        longitude_deg=latest_longitude_deg,
                    )
                return sample, bytes(buffer)

        chunk = transport.read(4096, min(DEFAULT_READ_TIMEOUT_S, max(deadline - time.monotonic(), 0.05)))
        if not chunk:
            continue
        buffer.extend(chunk)

    return None, bytes(buffer)


def parse_pressure_sentence(sentence: str) -> XCVarioPressureSample | None:
    normalized = str(sentence or "").strip()
    if not normalized:
        return None
    if normalized.startswith("$PXCV,"):
        return _parse_pxcv_sentence(normalized)
    if normalized.startswith("$POV,"):
        return _parse_pov_sentence(normalized)
    if normalized.startswith("!W,"):
        return _parse_cambridge_sentence(normalized)
    if normalized.startswith("$PTAS1,"):
        return _parse_ptas1_sentence(normalized)
    return None


def _parse_pxcv_sentence(sentence: str) -> XCVarioPressureSample | None:
    fields = _split_nmea_fields(sentence)
    if len(fields) < 8:
        return None
    device_qnh_hpa = _parse_float(fields[6])
    static_pressure_hpa = _parse_float(fields[7])
    if static_pressure_hpa is None:
        return None
    altitude_m = None
    if device_qnh_hpa is not None:
        try:
            altitude_m = static_pressure_to_qnh_altitude_m(device_qnh_hpa, static_pressure_hpa)
        except ValueError:
            altitude_m = None
    return XCVarioPressureSample(
        static_pressure_hpa=static_pressure_hpa,
        device_qnh_hpa=device_qnh_hpa,
        altitude_m=altitude_m,
        protocol="pxcv",
        raw_sentence=sentence,
    )


def _parse_pov_sentence(sentence: str) -> XCVarioPressureSample | None:
    fields = _split_nmea_fields(sentence)
    if len(fields) < 2:
        return None

    values: dict[str, str] = {}
    index = 0
    while index + 1 < len(fields):
        key = fields[index].strip().upper()
        values[key] = fields[index + 1].strip()
        index += 2

    static_pressure_hpa = _parse_float(values.get("P"))
    if static_pressure_hpa is None:
        return None

    return XCVarioPressureSample(
        static_pressure_hpa=static_pressure_hpa,
        device_qnh_hpa=None,
        altitude_m=None,
        protocol="pov",
        raw_sentence=sentence,
    )


def _parse_cambridge_sentence(sentence: str) -> XCVarioPressureSample | None:
    fields = _split_nmea_fields(sentence)
    if len(fields) < 5:
        return None

    raw_altitude_m = _parse_float(fields[3])
    device_qnh_hpa = _parse_float(fields[4])
    if raw_altitude_m is None or device_qnh_hpa is None:
        return None

    altitude_m = raw_altitude_m - 1000.0
    try:
        static_pressure_hpa = qnh_altitude_to_static_pressure_hpa(device_qnh_hpa, altitude_m)
    except ValueError:
        return None

    return XCVarioPressureSample(
        static_pressure_hpa=static_pressure_hpa,
        device_qnh_hpa=device_qnh_hpa,
        altitude_m=altitude_m,
        protocol="cambridge",
        raw_sentence=sentence,
    )


def _parse_ptas1_sentence(sentence: str) -> XCVarioPressureSample | None:
    fields = _split_nmea_fields(sentence)
    if len(fields) < 3:
        return None

    altitude_feet = _parse_float(fields[2])
    if altitude_feet is None:
        return None

    altitude_m = (altitude_feet - 2000.0) * 0.3048
    try:
        static_pressure_hpa = qnh_altitude_to_static_pressure_hpa(STANDARD_QNH_HPA, altitude_m)
    except ValueError:
        return None

    return XCVarioPressureSample(
        static_pressure_hpa=static_pressure_hpa,
        device_qnh_hpa=STANDARD_QNH_HPA,
        altitude_m=altitude_m,
        protocol="ptas1",
        raw_sentence=sentence,
    )


def _parse_gps_sentence(sentence: str) -> tuple[float, float] | None:
    normalized = str(sentence or "").strip()
    if normalized.startswith("$GPRMC,"):
        return _parse_gprmc_sentence(normalized)
    if normalized.startswith("$GPGGA,"):
        return _parse_gpgga_sentence(normalized)
    return None


def _parse_gprmc_sentence(sentence: str) -> tuple[float, float] | None:
    fields = _split_nmea_fields(sentence)
    if len(fields) < 6 or fields[1].upper() != "A":
        return None
    latitude_deg = _parse_nmea_coordinate(fields[2], fields[3], degree_digits=2)
    longitude_deg = _parse_nmea_coordinate(fields[4], fields[5], degree_digits=3)
    if latitude_deg is None or longitude_deg is None:
        return None
    return latitude_deg, longitude_deg


def _parse_gpgga_sentence(sentence: str) -> tuple[float, float] | None:
    fields = _split_nmea_fields(sentence)
    if len(fields) < 6:
        return None
    fix_quality = str(fields[5] or "").strip()
    if not fix_quality or fix_quality == "0":
        return None
    latitude_deg = _parse_nmea_coordinate(fields[1], fields[2], degree_digits=2)
    longitude_deg = _parse_nmea_coordinate(fields[3], fields[4], degree_digits=3)
    if latitude_deg is None or longitude_deg is None:
        return None
    return latitude_deg, longitude_deg


def _split_nmea_fields(sentence: str) -> list[str]:
    body = sentence.strip()
    if "*" in body:
        body = body.split("*", 1)[0]
    if "," not in body:
        return []
    _prefix, remainder = body.split(",", 1)
    return [field.strip() for field in remainder.split(",")]


def _parse_nmea_coordinate(value: object, hemisphere: object, *, degree_digits: int) -> float | None:
    raw_value = str(value or "").strip()
    raw_hemisphere = str(hemisphere or "").strip().upper()
    if not raw_value or raw_hemisphere not in {"N", "S", "E", "W"}:
        return None
    if len(raw_value) <= degree_digits:
        return None
    degrees_text = raw_value[:degree_digits]
    minutes_text = raw_value[degree_digits:]
    degrees = _parse_float(degrees_text)
    minutes = _parse_float(minutes_text)
    if degrees is None or minutes is None:
        return None
    coordinate = degrees + minutes / 60.0
    if raw_hemisphere in {"S", "W"}:
        coordinate *= -1.0
    return coordinate


def _parse_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None
