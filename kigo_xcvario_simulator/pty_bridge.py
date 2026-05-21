"""Expose a TCP stream as a stable PTY path for XCSoar/Kigo profiles."""

from __future__ import annotations

import argparse
import errno
import json
import os
import pty
import selectors
import signal
import socket
import termios
import time
import tty
from pathlib import Path


DEFAULT_RECONNECT_DELAY_S = 1.0
DEFAULT_SOCKET_TIMEOUT_S = 0.5
DEFAULT_STATUS_INTERVAL_S = 1.0
DEFAULT_MAX_BUFFER_BYTES = 256 * 1024


class PtyTcpBridge:
    def __init__(
        self,
        *,
        serial_path: Path,
        tcp_host: str,
        tcp_port: int,
        reconnect_delay_s: float = DEFAULT_RECONNECT_DELAY_S,
        socket_timeout_s: float = DEFAULT_SOCKET_TIMEOUT_S,
        status_path: Path | None = None,
        max_buffer_bytes: int = DEFAULT_MAX_BUFFER_BYTES,
    ) -> None:
        self.serial_path = Path(serial_path)
        self.tcp_host = str(tcp_host)
        self.tcp_port = int(tcp_port)
        self.reconnect_delay_s = max(0.1, float(reconnect_delay_s))
        self.socket_timeout_s = max(0.1, float(socket_timeout_s))
        self.status_path = Path(status_path) if status_path is not None else self.serial_path.with_name(
            f"{self.serial_path.name}.status.json"
        )
        self.max_buffer_bytes = max(4096, int(max_buffer_bytes))
        self._stop_requested = False
        self._started_wall_s = time.time()
        self._last_status_write_s = 0.0
        self._tcp_connected = False
        self._last_connect_error = ""
        self._last_connect_attempt_wall_s: float | None = None
        self._last_connected_wall_s: float | None = None
        self._bytes_tcp_to_pty = 0
        self._bytes_pty_to_tcp = 0
        self._master_fd, self._slave_fd = pty.openpty()
        self._slave_name = os.ttyname(self._slave_fd)
        self._configure_raw_fd(self._master_fd)
        self._configure_raw_fd(self._slave_fd)
        os.set_blocking(self._master_fd, False)
        self._install_serial_symlink()

    @property
    def slave_name(self) -> str:
        return self._slave_name

    def run_forever(self) -> int:
        self._install_signal_handlers()
        self._write_status(force=True)
        while not self._stop_requested:
            sock = self._connect_socket()
            if sock is None:
                time.sleep(self.reconnect_delay_s)
                continue
            try:
                self._relay_loop(sock)
            finally:
                self._mark_disconnected("")
                try:
                    sock.close()
                except OSError:
                    pass
                self._write_status(force=True)
        return 0

    def _connect_socket(self) -> socket.socket | None:
        self._last_connect_attempt_wall_s = time.time()
        self._write_status(force=True)
        try:
            sock = socket.create_connection((self.tcp_host, self.tcp_port), timeout=self.socket_timeout_s)
        except OSError as exc:
            self._mark_disconnected(str(exc))
            self._write_status(force=True)
            return None
        sock.setblocking(False)
        self._tcp_connected = True
        self._last_connect_error = ""
        self._last_connected_wall_s = time.time()
        self._write_status(force=True)
        return sock

    def _relay_loop(self, sock: socket.socket) -> None:
        selector = selectors.DefaultSelector()
        socket_to_pty = bytearray()
        pty_to_socket = bytearray()
        selector.register(sock, selectors.EVENT_READ, "socket")
        selector.register(self._master_fd, selectors.EVENT_READ, "pty")
        try:
            while not self._stop_requested:
                selector.modify(
                    sock,
                    selectors.EVENT_READ | (selectors.EVENT_WRITE if pty_to_socket else 0),
                    "socket",
                )
                selector.modify(
                    self._master_fd,
                    selectors.EVENT_READ | (selectors.EVENT_WRITE if socket_to_pty else 0),
                    "pty",
                )
                ready = selector.select(timeout=0.5)
                if not ready:
                    self._write_status()
                    continue
                for key, mask in ready:
                    if key.data == "socket":
                        if mask & selectors.EVENT_READ and not self._read_socket_to_buffer(sock, socket_to_pty):
                            return
                        if mask & selectors.EVENT_WRITE and not self._flush_buffer_to_socket(sock, pty_to_socket):
                            return
                    elif key.data == "pty":
                        if mask & selectors.EVENT_READ and not self._read_pty_to_buffer(pty_to_socket):
                            return
                        if mask & selectors.EVENT_WRITE and not self._flush_buffer_to_pty(socket_to_pty):
                            return
                self._write_status()
        finally:
            selector.close()

    def _pump_socket_to_pty(self, sock: socket.socket) -> bool:
        pending = bytearray()
        if not self._read_socket_to_buffer(sock, pending):
            return False
        return self._flush_buffer_to_pty(pending)

    def _pump_pty_to_socket(self, sock: socket.socket) -> bool:
        pending = bytearray()
        if not self._read_pty_to_buffer(pending):
            return False
        return self._flush_buffer_to_socket(sock, pending)

    def _read_socket_to_buffer(self, sock: socket.socket, pending: bytearray) -> bool:
        try:
            payload = sock.recv(4096)
        except BlockingIOError:
            return True
        except OSError as exc:
            self._mark_disconnected(str(exc))
            return False
        if not payload:
            self._mark_disconnected("tcp socket closed")
            return False
        _append_bounded(pending, payload, getattr(self, "max_buffer_bytes", DEFAULT_MAX_BUFFER_BYTES))
        return True

    def _read_pty_to_buffer(self, pending: bytearray) -> bool:
        try:
            payload = os.read(self._master_fd, 4096)
        except BlockingIOError:
            return True
        except OSError as exc:
            if exc.errno in {errno.EIO, errno.EBADF}:
                return True
            return False
        if not payload:
            return True
        _append_bounded(pending, payload, getattr(self, "max_buffer_bytes", DEFAULT_MAX_BUFFER_BYTES))
        return True

    def _flush_buffer_to_pty(self, pending: bytearray) -> bool:
        if not pending:
            return True
        try:
            written = os.write(self._master_fd, pending)
        except BlockingIOError:
            return True
        except OSError as exc:
            if exc.errno in {errno.EIO, errno.EBADF}:
                pending.clear()
                return True
            return False
        if written > 0:
            del pending[:written]
            self._bytes_tcp_to_pty += written
        return True

    def _flush_buffer_to_socket(self, sock: socket.socket, pending: bytearray) -> bool:
        if not pending:
            return True
        try:
            sent = sock.send(pending)
        except BlockingIOError:
            return True
        except OSError as exc:
            self._mark_disconnected(str(exc))
            return False
        if sent > 0:
            del pending[:sent]
            self._bytes_pty_to_tcp += sent
        return True

    def _install_signal_handlers(self) -> None:
        def _request_stop(_signum, _frame) -> None:
            self._stop_requested = True

        signal.signal(signal.SIGINT, _request_stop)
        signal.signal(signal.SIGTERM, _request_stop)

    def _install_serial_symlink(self) -> None:
        self.serial_path.parent.mkdir(parents=True, exist_ok=True)
        if self.serial_path.exists() or self.serial_path.is_symlink():
            self.serial_path.unlink()
        self.serial_path.symlink_to(self._slave_name)

    def _mark_disconnected(self, error: str) -> None:
        self._tcp_connected = False
        if error:
            self._last_connect_error = error

    def _write_status(self, *, force: bool = False) -> None:
        now_s = time.time()
        if not force and now_s - self._last_status_write_s < DEFAULT_STATUS_INTERVAL_S:
            return
        self._last_status_write_s = now_s
        payload = {
            "serial_path": str(self.serial_path),
            "slave_name": self._slave_name,
            "tcp_host": self.tcp_host,
            "tcp_port": self.tcp_port,
            "tcp_connected": self._tcp_connected,
            "last_connect_error": self._last_connect_error,
            "last_connect_attempt_utc_s": self._last_connect_attempt_wall_s,
            "last_connected_utc_s": self._last_connected_wall_s,
            "uptime_s": max(0.0, now_s - self._started_wall_s),
            "bytes_tcp_to_pty": self._bytes_tcp_to_pty,
            "bytes_pty_to_tcp": self._bytes_pty_to_tcp,
            "stop_requested": self._stop_requested,
        }
        try:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.status_path.with_name(f"{self.status_path.name}.tmp")
            tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            os.replace(tmp_path, self.status_path)
        except OSError:
            return

    @staticmethod
    def _configure_raw_fd(fd: int) -> None:
        tty.setraw(fd)
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[3] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bridge a TCP simulator stream to a PTY symlink path.")
    parser.add_argument("--serial-path", required=True, help="Symlink path exposed to XCSoar/Kigo, e.g. /tmp/kigo-sim/xcvario")
    parser.add_argument("--tcp-host", default="127.0.0.1", help="TCP host of the simulator runtime.")
    parser.add_argument("--tcp-port", required=True, type=int, help="TCP port of the simulator runtime.")
    parser.add_argument("--reconnect-delay", type=float, default=DEFAULT_RECONNECT_DELAY_S, help="Reconnect delay in seconds.")
    parser.add_argument("--status-path", default="", help="Optional JSON status file path. Defaults to <serial-path>.status.json.")
    args = parser.parse_args(argv)

    bridge = PtyTcpBridge(
        serial_path=Path(args.serial_path),
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
        reconnect_delay_s=args.reconnect_delay,
        status_path=Path(args.status_path) if args.status_path else None,
    )
    print(f"PTY bridge ready: {args.serial_path} -> {bridge.slave_name} -> {args.tcp_host}:{args.tcp_port}")
    return bridge.run_forever()


def _append_bounded(buffer: bytearray, payload: bytes, max_bytes: int) -> None:
    buffer.extend(payload)
    overflow = len(buffer) - max_bytes
    if overflow > 0:
        del buffer[:overflow]


if __name__ == "__main__":
    raise SystemExit(main())
