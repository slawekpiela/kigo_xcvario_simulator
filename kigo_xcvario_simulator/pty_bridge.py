"""Expose a TCP stream as a stable PTY path for XCSoar/Kigo profiles."""

from __future__ import annotations

import argparse
import errno
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


class PtyTcpBridge:
    def __init__(
        self,
        *,
        serial_path: Path,
        tcp_host: str,
        tcp_port: int,
        reconnect_delay_s: float = DEFAULT_RECONNECT_DELAY_S,
        socket_timeout_s: float = DEFAULT_SOCKET_TIMEOUT_S,
    ) -> None:
        self.serial_path = Path(serial_path)
        self.tcp_host = str(tcp_host)
        self.tcp_port = int(tcp_port)
        self.reconnect_delay_s = max(0.1, float(reconnect_delay_s))
        self.socket_timeout_s = max(0.1, float(socket_timeout_s))
        self._stop_requested = False
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
        while not self._stop_requested:
            sock = self._connect_socket()
            if sock is None:
                time.sleep(self.reconnect_delay_s)
                continue
            try:
                self._relay_loop(sock)
            finally:
                try:
                    sock.close()
                except OSError:
                    pass
        return 0

    def _connect_socket(self) -> socket.socket | None:
        try:
            sock = socket.create_connection((self.tcp_host, self.tcp_port), timeout=self.socket_timeout_s)
        except OSError:
            return None
        sock.setblocking(False)
        return sock

    def _relay_loop(self, sock: socket.socket) -> None:
        selector = selectors.DefaultSelector()
        selector.register(sock, selectors.EVENT_READ, "socket")
        selector.register(self._master_fd, selectors.EVENT_READ, "pty")
        try:
            while not self._stop_requested:
                ready = selector.select(timeout=0.5)
                if not ready:
                    continue
                for key, _mask in ready:
                    if key.data == "socket":
                        if not self._pump_socket_to_pty(sock):
                            return
                    elif key.data == "pty":
                        if not self._pump_pty_to_socket(sock):
                            return
        finally:
            selector.close()

    def _pump_socket_to_pty(self, sock: socket.socket) -> bool:
        try:
            payload = sock.recv(4096)
        except BlockingIOError:
            return True
        except OSError:
            return False
        if not payload:
            return False
        try:
            os.write(self._master_fd, payload)
        except BlockingIOError:
            return True
        except OSError as exc:
            if exc.errno in {errno.EIO, errno.EBADF}:
                return True
            return False
        return True

    def _pump_pty_to_socket(self, sock: socket.socket) -> bool:
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
        try:
            sock.sendall(payload)
        except OSError:
            return False
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
    args = parser.parse_args(argv)

    bridge = PtyTcpBridge(
        serial_path=Path(args.serial_path),
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
        reconnect_delay_s=args.reconnect_delay,
    )
    print(f"PTY bridge ready: {args.serial_path} -> {bridge.slave_name} -> {args.tcp_host}:{args.tcp_port}")
    return bridge.run_forever()


if __name__ == "__main__":
    raise SystemExit(main())
