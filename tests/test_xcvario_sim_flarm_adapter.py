import socket
import time
import unittest

from kigo_xcvario_simulator.contracts import OwnshipState, SimulationSnapshot, TrafficContact
from kigo_xcvario_simulator.flarm_adapter import FlarmTcpAdapter
from kigo_xcvario_simulator.state import FlightPhase, HealthState, RuntimeState


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
        traffic=(
            TrafficContact("TFC-01", 123.0, -45.0, 67.0, 90.0, 1.5, 1),
            TrafficContact("TFC-02", -220.0, 340.0, -80.0, 45.0, -0.5, 0),
        ),
        preset_id="straight",
        seed=7,
        sim_time_s=1.0,
        health=HealthState.READY,
    )


class FlarmAdapterTests(unittest.TestCase):
    def test_client_receives_pflaa_and_pflau_sentences(self):
        adapter = FlarmTcpAdapter(bind_host="127.0.0.1", port=0)
        adapter.start()
        self.addCleanup(adapter.stop)

        client = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(client.close)
        time.sleep(0.05)

        adapter.publish_snapshot(_snapshot())
        payload = client.recv(4096).decode("ascii")

        self.assertIn("$PFLAU,", payload)
        self.assertIn("$PFLAA,", payload)
        self.assertIn("TFC-01", payload)

    def test_new_client_can_reconnect_and_receive_future_payload(self):
        adapter = FlarmTcpAdapter(bind_host="127.0.0.1", port=0)
        adapter.start()
        self.addCleanup(adapter.stop)

        first = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        first.close()
        second = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(second.close)
        time.sleep(0.05)

        adapter.publish_snapshot(_snapshot())
        payload = second.recv(4096).decode("ascii")

        self.assertIn("$PFLAU,", payload)

    def test_multiple_clients_receive_same_flarm_stream(self):
        adapter = FlarmTcpAdapter(bind_host="127.0.0.1", port=0)
        adapter.start()
        self.addCleanup(adapter.stop)

        first = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        second = socket.create_connection(("127.0.0.1", adapter.bound_port), timeout=1.0)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        time.sleep(0.05)

        adapter.publish_snapshot(_snapshot())
        first_payload = first.recv(4096).decode("ascii")
        second_payload = second.recv(4096).decode("ascii")

        self.assertEqual(adapter.client_count, 2)
        self.assertIn("$PFLAU,", first_payload)
        self.assertIn("$PFLAA,", first_payload)
        self.assertIn("$PFLAU,", second_payload)
        self.assertIn("$PFLAA,", second_payload)


if __name__ == "__main__":
    unittest.main()
