"""Tests for the TCP-to-PTY bridge."""

from __future__ import annotations

import errno
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from kigo_xcvario_simulator.pty_bridge import PtyTcpBridge


class _FakeSocket:
    def recv(self, _size: int) -> bytes:
        return b"$GPRMC,test\r\n"


class PtyTcpBridgeTest(unittest.TestCase):
    def test_full_pty_buffer_does_not_drop_tcp_connection(self) -> None:
        bridge = object.__new__(PtyTcpBridge)
        bridge._master_fd = 123

        with patch(
            "kigo_xcvario_simulator.pty_bridge.os.write",
            side_effect=BlockingIOError(errno.EAGAIN, "temporarily unavailable"),
        ):
            self.assertTrue(bridge._pump_socket_to_pty(_FakeSocket()))

    def test_partial_pty_write_keeps_unwritten_bytes_buffered(self) -> None:
        bridge = object.__new__(PtyTcpBridge)
        bridge._master_fd = 123
        bridge._bytes_tcp_to_pty = 0
        pending = bytearray(b"abcdef")

        with patch("kigo_xcvario_simulator.pty_bridge.os.write", return_value=3):
            self.assertTrue(bridge._flush_buffer_to_pty(pending))

        self.assertEqual(pending, b"def")
        self.assertEqual(bridge._bytes_tcp_to_pty, 3)

    def test_status_file_reports_tcp_connection_and_counters(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "xcvario.status.json"
            bridge = object.__new__(PtyTcpBridge)
            bridge.serial_path = Path(tmp_dir) / "xcvario"
            bridge.status_path = status_path
            bridge._slave_name = "/dev/pts/11"
            bridge.tcp_host = "127.0.0.1"
            bridge.tcp_port = 4353
            bridge._tcp_connected = True
            bridge._last_connect_error = ""
            bridge._last_connect_attempt_wall_s = 123.0
            bridge._last_connected_wall_s = 124.0
            bridge._started_wall_s = 100.0
            bridge._last_status_write_s = 0.0
            bridge._bytes_tcp_to_pty = 120
            bridge._bytes_pty_to_tcp = 7
            bridge._stop_requested = False

            bridge._write_status(force=True)

            payload = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["tcp_connected"])
            self.assertEqual(payload["bytes_tcp_to_pty"], 120)
            self.assertEqual(payload["bytes_pty_to_tcp"], 7)


if __name__ == "__main__":
    unittest.main()
