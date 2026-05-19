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
        self._client_sockets: list[socket.socket] = []
        self.bound_port = int(port)

    @property
    def client_connected(self) -> bool:
        with self._lock:
            return bool(self._client_sockets)

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._client_sockets)

    @property
    def client_connections(self) -> tuple[dict[str, object], ...]:
        with self._lock:
            client_sockets = tuple(self._client_sockets)
        return tuple(_socket_connection_metadata(client_socket) for client_socket in client_sockets)

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
            client_sockets = tuple(self._client_sockets)
            self._client_sockets.clear()
        if server_socket is not None:
            try:
                server_socket.close()
            except OSError:
                pass
        for client_socket in client_sockets:
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
                self._client_sockets.append(client_socket)

    def _send(self, payload: bytes) -> None:
        with self._lock:
            client_sockets = tuple(self._client_sockets)
        if not client_sockets:
            return
        for client_socket in client_sockets:
            try:
                client_socket.sendall(payload)
            except OSError:
                self._remove_client(client_socket)

    def _remove_client(self, client_socket: socket.socket) -> None:
        with self._lock:
            if client_socket not in self._client_sockets:
                return
            self._client_sockets.remove(client_socket)
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


def _socket_connection_metadata(client_socket: socket.socket) -> dict[str, object]:
    local_host, local_port = _socket_endpoint(client_socket, local=True)
    peer_host, peer_port = _socket_endpoint(client_socket, local=False)
    return {
        "local": _format_endpoint(local_host, local_port),
        "local_host": local_host,
        "local_port": local_port,
        "peer": _format_endpoint(peer_host, peer_port),
        "peer_host": peer_host,
        "peer_port": peer_port,
    }


def _socket_endpoint(client_socket: socket.socket, *, local: bool) -> tuple[str, int | None]:
    try:
        endpoint = client_socket.getsockname() if local else client_socket.getpeername()
    except OSError:
        return "unknown", None
    if not endpoint:
        return "unknown", None
    return str(endpoint[0]), int(endpoint[1]) if len(endpoint) > 1 else None


def _format_endpoint(host: str, port: int | None) -> str:
    return f"{host}:{port}" if port is not None else host
