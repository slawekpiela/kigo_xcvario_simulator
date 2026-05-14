"""Tests for the TCP-to-PTY bridge."""

from __future__ import annotations

import errno
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


if __name__ == "__main__":
    unittest.main()
