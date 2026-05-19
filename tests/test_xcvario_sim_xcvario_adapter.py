from dataclasses import replace
import socket
import time
import unittest

from kigo_xcvario_simulator.contracts import OwnshipState, SimulationSnapshot, WindState
from kigo_xcvario_simulator.nmea import nmea_checksum
from kigo_xcvario_simulator.state import FlightPhase, HealthState, RuntimeState
from kigo_xcvario_simulator.xcvario_adapter import XcvarioTcpAdapter
from kigo_xcvario_simulator.xcvario_polar import get_xcvario_polar


def _snapshot() -> SimulationSnapshot:
    return SimulationSnapshot(
        runtime_state=RuntimeState.RUNNING,
        ownship=OwnshipState(
            timestamp_utc="2026-05-08T12:00:00.000Z",
            latitude_deg=49.83833,
            longitude_deg=19.00202,
            gps_altitude_m=401.0,
            static_pressure_hpa=965.43,
            device_qnh_hpa=1019.8,
            vertical_speed_ms=2.35,
            speed_kmh=90.0,
            track_deg=84.4,
            on_ground=False,
            phase=FlightPhase.STRAIGHT,
        ),
        traffic=(),
        wind=WindState(direction_deg=270.0, speed_kmh=25.5),
        preset_id="straight",
        seed=7,
        sim_time_s=1.0,
        health=HealthState.READY,
    )


class XcvarioAdapterTests(unittest.TestCase):
    def test_client_receives_sentences_and_qnh_command_is_forwarded(self):
        received_qnh: list[float] = []
        received_altitudes: list[float] = []
        adapter = XcvarioTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
            on_qnh_command=received_qnh.append,
            on_altitude_command=received_altitudes.append,
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        adapter.publish_snapshot(_snapshot())
        payload = client.recv(4096).decode("ascii")
        qnh_command = f"!g,q999*{nmea_checksum('!g,q999'):02X}\r\n".encode("ascii")
        client.sendall(qnh_command)
        altitude_command = f"!g,a875*{nmea_checksum('!g,a875'):02X}\r\n".encode("ascii")
        client.sendall(altitude_command)
        time.sleep(0.05)

        self.assertIn("$GPRMC,", payload)
        self.assertIn("$GPGGA,", payload)
        self.assertIn("$PXCV,2.4,0.00,0,1.000,0,18.0,1019.8,965.4,361.0", payload)
        self.assertIn("$POV,P,965.4,Q,361.0,E,2.4,T,18.0*", payload)
        self.assertIn("$WIMWV,270.0,T,25.5,K,A*", payload)
        self.assertEqual(received_qnh, [999.0])
        self.assertEqual(received_altitudes, [875.0])

    def test_cai302_style_commands_update_following_xcvario_frames(self):
        adapter = XcvarioTcpAdapter(bind_host="127.0.0.1", port=0, polar=get_xcvario_polar("DG 800B/15"))
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        client.sendall(b"!g,m30\r")
        client.sendall(b"!g,u95\r")
        client.sendall(b"!g,b5.000\r")
        time.sleep(0.05)

        adapter.publish_snapshot(_snapshot())
        payload = client.recv(4096).decode("ascii")

        self.assertIn("$PXCV,2.4,1.50,5,1.121,0,18.0,1019.8,965.4,361.0", payload)

    def test_oat_setting_updates_following_xcvario_frames(self):
        adapter = XcvarioTcpAdapter(bind_host="127.0.0.1", port=0, polar=get_xcvario_polar("DG 800B/15"))
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        adapter.set_oat_c(7.5)
        adapter.publish_snapshot(_snapshot())
        payload = client.recv(4096).decode("ascii")

        self.assertEqual(adapter.oat_c, 7.5)
        self.assertIn("$PXCV,2.4,0.00,0,1.000,0,7.5,1019.8,965.4,", payload)
        self.assertIn("$POV,P,965.4,Q,", payload)
        self.assertIn(",E,2.4,T,7.5*", payload)

    def test_gprmc_speed_is_adjusted_by_true_wind(self):
        adapter = XcvarioTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
            gps_every_baro_frames=1,
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        base_ownship = replace(_snapshot().ownship, speed_kmh=100.0, track_deg=90.0)
        adapter.publish_snapshot(
            replace(
                _snapshot(),
                ownship=base_ownship,
                wind=WindState(direction_deg=90.0, speed_kmh=20.0),
            )
        )
        headwind_payload = _recv_until(client, "$GPRMC,", expected_count=1)

        adapter.publish_snapshot(
            replace(
                _snapshot(),
                ownship=base_ownship,
                wind=WindState(direction_deg=270.0, speed_kmh=20.0),
            )
        )
        tailwind_payload = _recv_until(client, "$GPRMC,", expected_count=1)

        self.assertEqual(_gprmc_speed_knots(headwind_payload), 43.2)
        self.assertEqual(_gprmc_speed_knots(tailwind_payload), 64.8)

    def test_gprmc_speed_and_track_include_crosswind(self):
        adapter = XcvarioTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
            gps_every_baro_frames=1,
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        adapter.publish_snapshot(
            replace(
                _snapshot(),
                ownship=replace(_snapshot().ownship, speed_kmh=100.0, track_deg=90.0),
                wind=WindState(direction_deg=0.0, speed_kmh=20.0),
            )
        )
        payload = _recv_until(client, "$GPRMC,", expected_count=1)

        self.assertEqual(_gprmc_speed_knots(payload), 55.1)
        self.assertEqual(_gprmc_track_deg(payload), 101.3)

    def test_gprmc_ignores_wind_for_ground_roll(self):
        adapter = XcvarioTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
            gps_every_baro_frames=1,
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        adapter.publish_snapshot(
            replace(
                _snapshot(),
                ownship=replace(_snapshot().ownship, speed_kmh=24.0, track_deg=90.0, on_ground=True),
                wind=WindState(direction_deg=0.0, speed_kmh=40.0),
            )
        )
        payload = _recv_until(client, "$GPRMC,", expected_count=1)

        self.assertEqual(_gprmc_speed_knots(payload), 13.0)
        self.assertEqual(_gprmc_track_deg(payload), 90.0)

    def test_multiple_clients_receive_same_xcvario_stream(self):
        adapter = XcvarioTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
            on_qnh_command=None,
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        first = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(first.close)
        second = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(second.close)
        time.sleep(0.05)

        adapter.publish_snapshot(_snapshot())
        first_payload = _recv_until(first, "$PXCV,", expected_count=1)
        second_payload = _recv_until(second, "$PXCV,", expected_count=1)

        self.assertEqual(adapter.client_count, 2)
        self.assertIn("$PXCV,", first_payload)
        self.assertIn("$POV,", first_payload)
        self.assertIn("$WIMWV,", first_payload)
        self.assertIn("$PXCV,", second_payload)
        self.assertIn("$POV,", second_payload)
        self.assertIn("$WIMWV,", second_payload)

    def test_circling_output_altitude_advances_by_vario_value_per_publish(self):
        adapter = XcvarioTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
            gps_every_baro_frames=1,
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)
        circling_snapshot = replace(
            _snapshot(),
            ownship=replace(
                _snapshot().ownship,
                phase=FlightPhase.CIRCLING_LEFT,
                gps_altitude_m=401.0,
                vertical_speed_ms=2.0,
            ),
        )

        adapter.publish_snapshot(circling_snapshot)
        adapter.publish_snapshot(circling_snapshot)
        payload = _recv_until(client, "$GPGGA,", expected_count=2)
        gga_altitudes = [
            float(line.split(",")[9])
            for line in payload.splitlines()
            if line.startswith("$GPGGA,")
        ]

        self.assertEqual(gga_altitudes[:2], [403.0, 405.0])

    def test_position_and_baro_sentences_follow_xcvario_capture_cadence(self):
        adapter = XcvarioTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
            gps_every_baro_frames=2,
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        for _ in range(5):
            adapter.publish_snapshot(_snapshot())
        payload = _recv_until(client, "$PXCV,", expected_count=5)

        self.assertEqual(payload.count("$PXCV,"), 5)
        self.assertEqual(payload.count("$POV,"), 5)
        self.assertEqual(payload.count("$WIMWV,"), 5)
        self.assertEqual(payload.count("$GPRMC,"), 3)
        self.assertEqual(payload.count("$GPGGA,"), 3)

    def test_client_connect_callback_runs_for_initial_connect_and_reconnect(self):
        connect_count = 0

        def on_connect() -> None:
            nonlocal connect_count
            connect_count += 1

        adapter = XcvarioTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
            on_client_connect=on_connect,
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        first = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(first.close)
        time.sleep(0.05)
        first.close()
        time.sleep(0.05)
        second = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(second.close)
        time.sleep(0.05)

        self.assertEqual(connect_count, 2)


def _recv_until(client: socket.socket, needle: str, *, expected_count: int) -> str:
    client.settimeout(1.0)
    chunks = []
    payload = ""
    while payload.count(needle) < expected_count:
        chunk = client.recv(8192).decode("ascii")
        if not chunk:
            break
        chunks.append(chunk)
        payload = "".join(chunks)
    return payload


def _gprmc_speed_knots(payload: str) -> float:
    return float(_gprmc_fields(payload)[7])


def _gprmc_track_deg(payload: str) -> float:
    return float(_gprmc_fields(payload)[8])


def _gprmc_fields(payload: str) -> list[str]:
    for line in payload.splitlines():
        if line.startswith("$GPRMC,"):
            return line.split(",")
    raise AssertionError("GPRMC sentence not found.")


if __name__ == "__main__":
    unittest.main()
