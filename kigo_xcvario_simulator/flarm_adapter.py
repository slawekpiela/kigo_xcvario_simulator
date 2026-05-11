"""TCP listener that exposes traffic data as FLARM-compatible NMEA."""

from __future__ import annotations

import socket
from threading import Event, Lock, Thread

from .contracts import SimulationSnapshot
from .nmea import build_pflaa, build_pflau


class FlarmTcpAdapter:
    def __init__(self, *, bind_host: str, port: int) -> None:
        self._bind_host = bind_host
        self._requested_port = int(port)
        self._server_socket: socket.socket | None = None
        self._server_thread: Thread | None = None
        self._stop_event = Event()
        self._lock = Lock()
        self._client_socket: socket.socket | None = None
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
            self._server_thread = Thread(target=self._accept_loop, name="flarm-adapter", daemon=True)
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

    def publish_snapshot(self, snapshot: SimulationSnapshot) -> None:
        traffic = snapshot.traffic
        payload = [build_pflau(traffic)]
        payload.extend(build_pflaa(contact) for contact in traffic)
        self._send("".join(payload).encode("ascii"))

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
            with self._lock:
                previous_socket = self._client_socket
                self._client_socket = client_socket
            if previous_socket is not None:
                self._close_socket(previous_socket)

    def _send(self, payload: bytes) -> None:
        with self._lock:
            client_socket = self._client_socket
        if client_socket is None:
            return
        try:
            client_socket.sendall(payload)
        except OSError:
            with self._lock:
                if self._client_socket is client_socket:
                    self._client_socket = None
            self._close_socket(client_socket)

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
