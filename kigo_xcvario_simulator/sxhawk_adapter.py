"""TCP listener that exposes ownship data as LXNAV SxHAWK-compatible NMEA."""

from __future__ import annotations

import math

from .baro import STANDARD_QNH_HPA, qnh_altitude_to_static_pressure_hpa
from .contracts import SimulationSnapshot
from .nmea import build_gpgga, build_gprmc, build_lxwp0, build_lxwp1, build_lxwp2, build_lxwp3
from .xcvario_adapter import (
    DEFAULT_GPS_EVERY_BARO_FRAMES,
    XcvarioTcpAdapter,
    _command_value_text,
    _ownship_with_wind_adjusted_ground_velocity,
)
from .xcvario_polar import XcvarioPolar


DEFAULT_DEVICE_INFO_EVERY_BARO_FRAMES = 120
DEFAULT_SETTINGS_EVERY_BARO_FRAMES = 20
DEFAULT_VOLUME_PERCENT = 80
FEET_TO_METERS = 0.3048


class SxHawkTcpAdapter(XcvarioTcpAdapter):
    def __init__(
        self,
        *,
        bind_host: str,
        port: int,
        polar: XcvarioPolar,
        on_qnh_command=None,
        on_client_connect=None,
        gps_every_baro_frames: int = DEFAULT_GPS_EVERY_BARO_FRAMES,
        device_info_every_baro_frames: int = DEFAULT_DEVICE_INFO_EVERY_BARO_FRAMES,
        settings_every_baro_frames: int = DEFAULT_SETTINGS_EVERY_BARO_FRAMES,
    ) -> None:
        super().__init__(
            bind_host=bind_host,
            port=port,
            polar=polar,
            on_qnh_command=on_qnh_command,
            on_client_connect=on_client_connect,
            gps_every_baro_frames=gps_every_baro_frames,
            thread_name="sxhawk-adapter",
        )
        self._device_info_every_baro_frames = max(1, int(device_info_every_baro_frames))
        self._settings_every_baro_frames = max(1, int(settings_every_baro_frames))
        self._ballast_overload_factor = 1.0
        self._volume_percent = DEFAULT_VOLUME_PERCENT

    def publish_snapshot(self, snapshot: SimulationSnapshot) -> None:
        include_position = self._reserve_publish_frame()
        if include_position is None:
            return
        with self._lock:
            frame_index = max(0, self._baro_frame_index - 1)
            mac_cready_ms = self._mac_cready_ms
            bugs_degradation_percent = self._bugs_degradation_percent
            ballast_overload_factor = self._ballast_overload_factor
            volume_percent = self._volume_percent

        payload_parts = []
        if include_position:
            position_ownship = self._ownship_for_position_output(snapshot)
            gps_ownship = _ownship_with_wind_adjusted_ground_velocity(position_ownship, snapshot.wind)
            payload_parts.append(build_gprmc(gps_ownship))
            payload_parts.append(build_gpgga(position_ownship))

        payload_parts.append(build_lxwp0(snapshot.ownship, snapshot.wind))
        if frame_index == 0 or frame_index % self._device_info_every_baro_frames == 0:
            payload_parts.append(build_lxwp1())
            payload_parts.append(build_lxwp3(qnh_hpa=snapshot.ownship.device_qnh_hpa))
        if frame_index == 0 or frame_index % self._settings_every_baro_frames == 0:
            payload_parts.append(
                build_lxwp2(
                    mac_cready_ms=mac_cready_ms,
                    ballast_overload_factor=ballast_overload_factor,
                    bugs_degradation_percent=bugs_degradation_percent,
                    volume_percent=volume_percent,
                )
            )

        self._send("".join(payload_parts).encode("ascii"))

    def _handle_command(self, line: str) -> None:
        body = _nmea_body(line)
        if not body:
            super()._handle_command(line)
            return

        fields = body.split(",")
        sentence_type = fields[0].strip().upper()
        values = fields[1:]
        if sentence_type == "PFLX2":
            self._handle_pflx2_command(values)
        elif sentence_type == "PFLX3":
            self._handle_pflx3_command(values)
        elif sentence_type == "PLXV0":
            self._handle_plxv0_command(values)
        elif sentence_type != "PFLX0":
            super()._handle_command(line)

    def _handle_pflx2_command(self, fields: list[str]) -> None:
        mac_cready_ms = _parse_optional_float_at(fields, 0)
        ballast_overload_factor = _parse_optional_float_at(fields, 1)
        bugs_degradation_percent = _parse_optional_float_at(fields, 2)
        volume_percent = _parse_optional_float_at(fields, 6)
        with self._lock:
            if mac_cready_ms is not None:
                self._mac_cready_ms = max(0.0, mac_cready_ms)
            if ballast_overload_factor is not None:
                self._ballast_overload_factor = _clamp(ballast_overload_factor, 1.0, 1.6)
            if bugs_degradation_percent is not None:
                self._bugs_degradation_percent = int(_clamp(bugs_degradation_percent, 0.0, 30.0))
            if volume_percent is not None:
                self._volume_percent = int(_clamp(volume_percent, 0.0, 100.0))

    def _handle_pflx3_command(self, fields: list[str]) -> None:
        altitude_offset_ft = _parse_optional_float_at(fields, 0)
        if altitude_offset_ft is None:
            return
        pressure_altitude_m = -altitude_offset_ft * FEET_TO_METERS
        try:
            qnh_hpa = qnh_altitude_to_static_pressure_hpa(STANDARD_QNH_HPA, pressure_altitude_m)
        except ValueError:
            return
        self._notify_qnh_command(qnh_hpa)

    def _handle_plxv0_command(self, fields: list[str]) -> None:
        if len(fields) < 3:
            return
        name = fields[0].strip().upper()
        access_type = fields[1].strip().upper()
        if access_type != "W":
            return
        value_text = _command_value_text(",".join(fields[2:]))
        if not value_text:
            return
        if name == "MC":
            value = _parse_float(value_text)
            if value is not None:
                with self._lock:
                    self._mac_cready_ms = max(0.0, value)
        elif name == "BAL":
            value = _parse_float(value_text)
            if value is not None:
                with self._lock:
                    self._ballast_overload_factor = _clamp(value, 1.0, 1.6)
        elif name == "BUGS":
            value = _parse_float(value_text)
            if value is not None:
                with self._lock:
                    self._bugs_degradation_percent = int(_clamp(value, 0.0, 30.0))
        elif name == "QNH":
            value = _parse_float(value_text)
            if value is not None and math.isfinite(value):
                self._notify_qnh_command(value / 100.0)

    def _notify_qnh_command(self, qnh_hpa: float) -> None:
        callback = self._on_qnh_command
        if callback is None:
            return
        try:
            callback(float(qnh_hpa))
        except Exception:
            return


def _nmea_body(line: str) -> str:
    normalized = str(line or "").strip()
    if not normalized.startswith("$"):
        return ""
    return normalized[1:].split("*", 1)[0].strip()


def _parse_optional_float_at(fields: list[str], index: int) -> float | None:
    if index >= len(fields):
        return None
    return _parse_float(fields[index])


def _parse_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))
