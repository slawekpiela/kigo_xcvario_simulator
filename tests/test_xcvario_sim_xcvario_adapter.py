from dataclasses import replace
import socket
import time
import unittest

from kigo_xcvario_simulator.contracts import OwnshipState, SimulationSnapshot, WindState
from kigo_xcvario_simulator.flarm_passthrough import (
    MESSAGE_ACK,
    MESSAGE_GET_IGC_DATA,
    MESSAGE_GET_RECORD_INFO,
    MESSAGE_NACK,
    MESSAGE_PING,
    MESSAGE_SELECT_RECORD,
    FlarmPassthroughConnectionState,
    FlarmPassthroughSimulator,
    FlarmRecordedFlight,
    _build_frame,
    _pop_frame,
)
from kigo_xcvario_simulator.nmea import build_nmea_sentence
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
        self.assertIn("$HCHDM,84.4,M*", payload)
        self.assertIn("$PXCV,2.4,0.00,0,1.000,0,18.0,1019.8,965.4,361.0", payload)
        self.assertIn("$POV,P,965.4,Q,361.0,E,2.4,T,18.0*", payload)
        self.assertIn("$WIMWV,270.0,T,25.5,K,A*", payload)
        self.assertIn("$LXWP0,Y,90.0,401.0,2.35", payload)
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
        self.assertIn("$HCHDM,90.0,M*", payload)

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
        self.assertEqual(len(adapter.client_connections), 2)
        self.assertTrue(all(connection["peer_host"] == "127.0.0.1" for connection in adapter.client_connections))
        self.assertTrue(all(connection["local_port"] == adapter.bound_port for connection in adapter.client_connections))
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

    def test_circling_output_includes_smooth_ahrs_roll_angle(self):
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
        circling_ownship = replace(_snapshot().ownship, phase=FlightPhase.CIRCLING_LEFT)

        for sim_time_s in (0.0, 2.0, 4.0, 6.0):
            adapter.publish_snapshot(replace(_snapshot(), ownship=circling_ownship, sim_time_s=sim_time_s))
        payload = _recv_until(client, "$PXCV,", expected_count=4)
        roll_angles = _pxcv_roll_angles(payload)

        self.assertEqual(roll_angles, [-42.5, -50.0, -42.5, -35.0])
        self.assertTrue(all(35.0 <= abs(roll_angle) <= 50.0 for roll_angle in roll_angles))

        right_payload_snapshot = replace(_snapshot(), ownship=replace(circling_ownship, phase=FlightPhase.CIRCLING_RIGHT))
        adapter.publish_snapshot(replace(right_payload_snapshot, sim_time_s=6.0))
        right_payload = _recv_until(client, "$PXCV,", expected_count=1)
        self.assertEqual(_pxcv_roll_angles(right_payload), [35.0])

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
        self.assertEqual(payload.count("$LXWP0,"), 5)
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

    def test_flarm_declaration_commands_are_accepted_on_xcvario_link(self):
        adapter = XcvarioTcpAdapter(bind_host="127.0.0.1", port=0, polar=get_xcvario_polar("DG 800B/15"))
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        _send_nmea(client, "PFLAC,S,PILOT,SLAWEK")
        _send_nmea(client, "PFLAC,S,GLIDERID,SP-001")
        _send_nmea(client, "PFLAC,S,NEWTASK,Task")
        _send_nmea(client, "PFLAC,S,ADDWP,0000000N,00000000E,T")
        _send_nmea(client, "PFLAC,S,ADDWP,4983000N,01900202E,START")

        payload = _recv_until(client, "$PFLAC,A,", expected_count=5)
        declaration = adapter.flarm_declaration

        self.assertIn("$PFLAC,A,PILOT,SLAWEK*", payload)
        self.assertIn("$PFLAC,A,ADDWP,4983000N,01900202E,START*", payload)
        self.assertEqual(declaration["pilot"], "SLAWEK")
        self.assertEqual(declaration["aircraft_registration"], "SP-001")
        self.assertEqual(declaration["task_name"], "Task")
        self.assertEqual(
            declaration["waypoints"],
            ("0000000N,00000000E,T", "4983000N,01900202E,START"),
        )

    def test_flarm_binary_logger_readout_is_accepted_on_xcvario_link(self):
        flarm_passthrough = FlarmPassthroughSimulator(
            records=(
                FlarmRecordedFlight(
                    record_info="2026-05-08|12:00:00|00:15:00|SIM PILOT|SIM|Club",
                    igc_text=(
                        "AFLXSIMKIGO XCVario Simulator\r\n"
                        "HFDTE080526\r\n"
                        "HFPLTPILOTINCHARGE:SIM PILOT\r\n"
                        "B1200004983000N01900202EA0040100401\r\n"
                        "B1201004983100N01900500EA0045000450\r\n"
                    ),
                    source_name="synthetic-test.igc",
                ),
            )
        )
        adapter = XcvarioTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
            flarm_passthrough=flarm_passthrough,
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        _send_nmea(client, "PFLAX")
        request_state = FlarmPassthroughConnectionState()

        ping = _binary_request(MESSAGE_PING, request_state)
        client.sendall(ping)
        ping_response = _recv_binary_frame(client)
        self.assertEqual(ping_response[0], MESSAGE_ACK)
        self.assertEqual(int.from_bytes(ping_response[2][:2], "little"), 0)

        client.sendall(_binary_request(MESSAGE_SELECT_RECORD, request_state, b"\x00"))
        select_response = _recv_binary_frame(client)
        self.assertEqual(select_response[0], MESSAGE_ACK)

        client.sendall(_binary_request(MESSAGE_GET_RECORD_INFO, request_state))
        info_response = _recv_binary_frame(client)
        self.assertEqual(info_response[0], MESSAGE_ACK)
        self.assertIn(b"2026-05-08|12:00:00|00:15:00", info_response[2])

        client.sendall(_binary_request(MESSAGE_SELECT_RECORD, request_state, b"\x01"))
        end_of_list_response = _recv_binary_frame(client)
        self.assertEqual(end_of_list_response[0], MESSAGE_NACK)

        client.sendall(_binary_request(MESSAGE_SELECT_RECORD, request_state, b"\x00"))
        self.assertEqual(_recv_binary_frame(client)[0], MESSAGE_ACK)

        client.sendall(_binary_request(MESSAGE_GET_IGC_DATA, request_state))
        igc_response = _recv_binary_frame(client)
        self.assertEqual(igc_response[0], MESSAGE_ACK)
        self.assertEqual(igc_response[2][2], 100)
        self.assertIn(b"AFLXSIMKIGO XCVario Simulator", igc_response[2])
        self.assertTrue(igc_response[2].endswith(b"\x1a"))


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


def _pxcv_roll_angles(payload: str) -> list[float]:
    return [
        float(line.split(",")[10])
        for line in payload.splitlines()
        if line.startswith("$PXCV,") and line.split(",")[10]
    ]


def _send_nmea(client: socket.socket, body: str) -> None:
    client.sendall(build_nmea_sentence(body).encode("ascii"))


def _binary_request(message_type: int, state: FlarmPassthroughConnectionState, payload: bytes = b"") -> bytes:
    return _build_frame(message_type, payload, state)


def _recv_binary_frame(client: socket.socket) -> tuple[int, int, bytes]:
    client.settimeout(1.0)
    buffer = bytearray()
    while True:
        chunk = client.recv(8192)
        if not chunk:
            raise AssertionError("binary frame not found before connection closed")
        buffer.extend(chunk)
        frame = _pop_frame(buffer)
        if frame is not None:
            return frame


if __name__ == "__main__":
    unittest.main()
