from dataclasses import replace
import socket
import time
import unittest

from kigo_xcvario_simulator.contracts import OwnshipState, SimulationSnapshot, WindState
from kigo_xcvario_simulator.nmea import build_lxwp3, build_nmea_sentence
from kigo_xcvario_simulator.state import FlightPhase, HealthState, RuntimeState
from kigo_xcvario_simulator.sxhawk_adapter import SxHawkTcpAdapter
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


class SxHawkAdapterTests(unittest.TestCase):
    def test_client_receives_sxhawk_lx_sentences(self):
        adapter = SxHawkTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        adapter.publish_snapshot(_snapshot())
        payload = client.recv(4096).decode("ascii")

        self.assertIn("$GPRMC,", payload)
        self.assertIn("$GPGGA,", payload)
        self.assertIn("$LXWP0,Y,90.0,401.0,2.35,2.35,2.35,2.35,2.35,2.35,84.4,270.0,25.5*", payload)
        self.assertIn("$LXWP1,SxHAWK,SXSIM0001,I9.56/S9.54,SIM,*", payload)
        self.assertIn("$LXWP2,0.0,1.00,0,,,,80*", payload)
        self.assertIn("$LXWP3,", payload)

    def test_multiple_clients_receive_same_sxhawk_stream(self):
        adapter = SxHawkTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        first = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        second = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        time.sleep(0.05)

        adapter.publish_snapshot(_snapshot())
        first_payload = _recv_until(first, "$LXWP0,", expected_count=1)
        second_payload = _recv_until(second, "$LXWP0,", expected_count=1)

        self.assertEqual(adapter.client_count, 2)
        self.assertEqual(len(adapter.client_connections), 2)
        self.assertTrue(all(connection["peer_host"] == "127.0.0.1" for connection in adapter.client_connections))
        self.assertTrue(all(connection["local_port"] == adapter.bound_port for connection in adapter.client_connections))
        self.assertIn("$GPRMC,", first_payload)
        self.assertIn("$LXWP0,", first_payload)
        self.assertIn("$GPRMC,", second_payload)
        self.assertIn("$LXWP0,", second_payload)

    def test_lx_style_settings_commands_update_following_sxhawk_frames(self):
        received_qnh: list[float] = []
        adapter = SxHawkTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
            on_qnh_command=received_qnh.append,
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        client.sendall(build_nmea_sentence("PFLX2,1.5,1.20,7,,,,65").encode("ascii"))
        client.sendall(build_lxwp3(qnh_hpa=999.0).replace("$LXWP3", "$PFLX3", 1).encode("ascii"))
        time.sleep(0.05)

        adapter.publish_snapshot(_snapshot())
        payload = client.recv(4096).decode("ascii")

        self.assertIn("$LXWP2,1.5,1.20,7,,,,65*", payload)
        self.assertEqual(len(received_qnh), 1)
        self.assertAlmostEqual(received_qnh[0], 999.0, places=1)

    def test_plxv0_settings_commands_are_accepted_for_compatibility(self):
        received_qnh: list[float] = []
        received_altitudes: list[float] = []
        adapter = SxHawkTcpAdapter(
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

        client.sendall(build_nmea_sentence("PLXV0,MC,W,2.0").encode("ascii"))
        client.sendall(build_nmea_sentence("PLXV0,BAL,W,1.30").encode("ascii"))
        client.sendall(build_nmea_sentence("PLXV0,BUGS,W,9").encode("ascii"))
        client.sendall(build_nmea_sentence("PLXV0,QNH,W,100500").encode("ascii"))
        client.sendall(build_nmea_sentence("PLXV0,ALT,W,875").encode("ascii"))
        time.sleep(0.05)

        adapter.publish_snapshot(replace(_snapshot(), wind=WindState(direction_deg=90.0, speed_kmh=15.0)))
        payload = client.recv(4096).decode("ascii")

        self.assertIn("$LXWP2,2.0,1.30,9,,,,80*", payload)
        self.assertEqual(received_qnh, [1005.0])
        self.assertEqual(received_altitudes, [875.0])

    def test_lxwp0_uses_device_altitude_and_lxwp3_is_sent_when_qnh_changes(self):
        adapter = SxHawkTcpAdapter(
            bind_host="127.0.0.1",
            port=0,
            polar=get_xcvario_polar("DG 800B/15"),
            device_info_every_baro_frames=100,
        )
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        first = replace(_snapshot().ownship, device_altitude_m=456.0)
        changed_qnh = replace(first, device_qnh_hpa=995.5, device_altitude_m=612.0)
        adapter.publish_snapshot(replace(_snapshot(), ownship=first))
        client.recv(4096)

        adapter.publish_snapshot(replace(_snapshot(), ownship=changed_qnh))
        payload = client.recv(4096).decode("ascii")

        self.assertIn("$LXWP0,Y,90.0,612.0,2.35", payload)
        self.assertIn("$LXWP3,", payload)


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


if __name__ == "__main__":
    unittest.main()
