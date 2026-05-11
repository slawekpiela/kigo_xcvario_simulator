"""TCP listener that exposes ownship data as XCvario-compatible NMEA."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import socket
from threading import Event, Lock, Thread

from .contracts import SimulationSnapshot
from .baro import qnh_hpa_for_static_pressure, static_pressure_hpa_for_altitude
from .nmea import build_gpgga, build_gprmc, build_pov, build_pxcv, build_wimwv, dynamic_pressure_pa_for_speed
from .state import FlightPhase
from .xcvario_polar import XcvarioPolar


DEFAULT_GPS_EVERY_BARO_FRAMES = 2
DEFAULT_OAT_C = 18.0
DEFAULT_MAC_CREADY_MS = 0.0
DEFAULT_BUGS_DEGRADATION_PERCENT = 0
DEFAULT_BALLAST_FILL_FRACTION = 0.0
KNOTS_TO_MS = 0.514444


class XcvarioTcpAdapter:
    def __init__(
        self,
        *,
        bind_host: str,
        port: int,
        polar: XcvarioPolar,
        on_qnh_command: Callable[[float], object] | None = None,
        on_client_connect: Callable[[], object] | None = None,
        gps_every_baro_frames: int = DEFAULT_GPS_EVERY_BARO_FRAMES,
    ) -> None:
        self._bind_host = bind_host
        self._requested_port = int(port)
        self._polar = polar
        self._on_qnh_command = on_qnh_command
        self._on_client_connect = on_client_connect
        self._gps_every_baro_frames = max(1, int(gps_every_baro_frames))
        self._server_socket: socket.socket | None = None
        self._server_thread: Thread | None = None
        self._reader_thread: Thread | None = None
        self._stop_event = Event()
        self._lock = Lock()
        self._client_socket: socket.socket | None = None
        self._reported_ownship_altitude_m: float | None = None
        self._baro_frame_index = 0
        self._oat_c = DEFAULT_OAT_C
        self._mac_cready_ms = DEFAULT_MAC_CREADY_MS
        self._bugs_degradation_percent = DEFAULT_BUGS_DEGRADATION_PERCENT
        self._ballast_fill_fraction = DEFAULT_BALLAST_FILL_FRACTION
        self.bound_port = int(port)

    @property
    def client_connected(self) -> bool:
        with self._lock:
            return self._client_socket is not None

    def start(self) -> None:
        with self._lock:
            if self._server_socket is not None:
                return
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self._bind_host, self._requested_port))
            server_socket.listen(5)
            server_socket.settimeout(0.2)
            self._server_socket = server_socket
            self.bound_port = int(server_socket.getsockname()[1])
            self._stop_event.clear()
            self._server_thread = Thread(target=self._accept_loop, name="xcvario-adapter", daemon=True)
            self._server_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            server_socket = self._server_socket
            self._server_socket = None
            client_socket = self._client_socket
            self._client_socket = None
        if server_socket is not None:
            try:
                server_socket.close()
            except OSError:
                pass
        if client_socket is not None:
            self._close_socket(client_socket)
        if self._server_thread is not None:
            self._server_thread.join(timeout=1.0)
            self._server_thread = None
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)
            self._reader_thread = None

    def publish_snapshot(self, snapshot: SimulationSnapshot) -> None:
        include_position = self._reserve_publish_frame()
        if include_position is None:
            return
        with self._lock:
            oat_c = self._oat_c
            mac_cready_ms = self._mac_cready_ms
            bugs_degradation_percent = self._bugs_degradation_percent
            ballast_fill_fraction = self._ballast_fill_fraction
        ballast_overload_factor = self._polar.ballast_overload_factor(ballast_fill_fraction)
        dynamic_pressure_pa = dynamic_pressure_pa_for_speed(
            static_pressure_hpa=snapshot.ownship.static_pressure_hpa,
            speed_kmh=snapshot.ownship.speed_kmh,
            oat_c=oat_c,
        )

        payload_parts = []
        if include_position:
            position_ownship = self._ownship_for_position_output(snapshot)
            payload_parts.append(build_gprmc(position_ownship))
            payload_parts.append(build_gpgga(position_ownship))
        payload_parts.append(
            build_pxcv(
                snapshot.ownship,
                oat_c=oat_c,
                mac_cready_ms=mac_cready_ms,
                bugs_degradation_percent=bugs_degradation_percent,
                ballast_overload_factor=ballast_overload_factor,
                dynamic_pressure_pa=dynamic_pressure_pa,
            )
        )
        payload_parts.append(
            build_pov(
                snapshot.ownship,
                oat_c=oat_c,
                dynamic_pressure_pa=dynamic_pressure_pa,
            )
        )
        payload_parts.append(build_wimwv(snapshot.wind))
        payload = "".join(payload_parts).encode("ascii")
        self._send(payload)

    def _reserve_publish_frame(self) -> bool | None:
        with self._lock:
            if self._client_socket is None:
                return None
            include_position = self._baro_frame_index % self._gps_every_baro_frames == 0
            self._baro_frame_index += 1
            return include_position

    def _ownship_for_position_output(self, snapshot: SimulationSnapshot):
        ownship = snapshot.ownship
        if ownship.phase not in {FlightPhase.CIRCLING_LEFT, FlightPhase.CIRCLING_RIGHT}:
            with self._lock:
                self._reported_ownship_altitude_m = ownship.gps_altitude_m
            return ownship

        with self._lock:
            previous_altitude_m = self._reported_ownship_altitude_m
            if previous_altitude_m is None:
                previous_altitude_m = ownship.gps_altitude_m
            reported_altitude_m = previous_altitude_m + ownship.vertical_speed_ms
            self._reported_ownship_altitude_m = reported_altitude_m

        pressure_reference_qnh_hpa = qnh_hpa_for_static_pressure(
            ownship.static_pressure_hpa,
            ownship.gps_altitude_m,
        )
        return replace(
            ownship,
            gps_altitude_m=reported_altitude_m,
            static_pressure_hpa=static_pressure_hpa_for_altitude(
                reported_altitude_m,
                qnh_hpa=pressure_reference_qnh_hpa,
            ),
        )

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            server_socket = self._server_socket
            if server_socket is None:
                return
            try:
                client_socket, _address = server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            client_socket.settimeout(0.2)
            self._swap_client(client_socket)

    def _swap_client(self, client_socket: socket.socket) -> None:
        with self._lock:
            previous_socket = self._client_socket
            self._client_socket = client_socket
            self._reported_ownship_altitude_m = None
            self._baro_frame_index = 0
        if previous_socket is not None:
            self._close_socket(previous_socket)
        reader = Thread(target=self._reader_loop, args=(client_socket,), name="xcvario-adapter-reader", daemon=True)
        self._reader_thread = reader
        reader.start()
        self._notify_client_connect()

    def _reader_loop(self, client_socket: socket.socket) -> None:
        buffer = bytearray()
        while not self._stop_event.is_set():
            if not self._is_current_client(client_socket):
                break
            try:
                chunk = client_socket.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break
            buffer.extend(chunk)
            while True:
                separator_index = _find_separator(buffer)
                if separator_index < 0:
                    break
                line = bytes(buffer[:separator_index]).decode("ascii", "ignore").strip()
                del buffer[: separator_index + 1]
                self._handle_command(line)
        if self._is_current_client(client_socket):
            with self._lock:
                if self._client_socket is client_socket:
                    self._client_socket = None
        self._close_socket(client_socket)

    def _handle_command(self, line: str) -> None:
        if not line.startswith("!g,") or len(line) < 5:
            return
        command = line[3]
        value_text = _command_value_text(line[4:])
        if not value_text:
            return
        if command == "q":
            self._handle_qnh_command(value_text)
        elif command == "m":
            self._handle_mac_cready_command(value_text)
        elif command == "u":
            self._handle_bugs_command(value_text)
        elif command == "b":
            self._handle_ballast_command(value_text)

    def _handle_qnh_command(self, value_text: str) -> None:
        try:
            qnh_hpa = float(value_text)
        except ValueError:
            return
        callback = self._on_qnh_command
        if callback is None:
            return
        try:
            callback(qnh_hpa)
        except Exception:
            return

    def _handle_mac_cready_command(self, value_text: str) -> None:
        try:
            mc_knots = float(value_text) * 0.1
        except ValueError:
            return
        mc_ms = round(mc_knots * KNOTS_TO_MS * 10.0) / 10.0
        with self._lock:
            self._mac_cready_ms = max(0.0, mc_ms)

    def _handle_bugs_command(self, value_text: str) -> None:
        try:
            instrument_percent = int(float(value_text))
        except ValueError:
            return
        degradation_percent = max(0, 100 - instrument_percent)
        with self._lock:
            self._bugs_degradation_percent = min(30, degradation_percent)

    def _handle_ballast_command(self, value_text: str) -> None:
        try:
            ballast_command = float(value_text)
        except ValueError:
            return
        ballast_fill_fraction = max(0.0, min(10.0, ballast_command)) / 10.0
        with self._lock:
            self._ballast_fill_fraction = ballast_fill_fraction

    def _notify_client_connect(self) -> None:
        callback = self._on_client_connect
        if callback is None:
            return
        try:
            callback()
        except Exception:
            return

    def _send(self, payload: bytes) -> None:
        with self._lock:
            client_socket = self._client_socket
        if client_socket is None:
            return
        try:
            client_socket.sendall(payload)
        except OSError:
            if self._is_current_client(client_socket):
                with self._lock:
                    if self._client_socket is client_socket:
                        self._client_socket = None
            self._close_socket(client_socket)

    def _is_current_client(self, client_socket: socket.socket) -> bool:
        with self._lock:
            return self._client_socket is client_socket

    @staticmethod
    def _close_socket(client_socket: socket.socket) -> None:
        try:
            client_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            client_socket.close()
        except OSError:
            pass


def _find_separator(buffer: bytearray) -> int:
    for index, octet in enumerate(buffer):
        if octet in (10, 13):
            return index
    return -1


def _command_value_text(raw_value_text: str) -> str:
    return raw_value_text.split("*", 1)[0].strip()
