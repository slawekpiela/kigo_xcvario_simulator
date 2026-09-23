import concurrent.futures
from dataclasses import replace
import http.client
import json
from pathlib import Path
import socket
import threading
import time
import unittest
from unittest.mock import patch

from kigo_xcvario_simulator.config import load_runtime_config
from kigo_xcvario_simulator.online import Channel, OnlineServer, SessionRegistry, ApiError
from kigo_xcvario_simulator.state import RuntimeState

CONFIG = Path(__file__).resolve().parents[1] / "kigo_xcvario_simulator/examples/runtime.example.json"
PANEL_A = "a" * 32
PANEL_B = "b" * 32


class OnlineTests(unittest.TestCase):
    def setUp(self):
        self.registry = SessionRegistry(load_runtime_config(CONFIG), limit=3)
        self.server = OnlineServer(("127.0.0.1", 0), self.registry)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.registry.close()

    def post(self, path, payload, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request("POST", "/simulator/api/" + path, json.dumps(payload),
                         {"Content-Type": "application/json", **(headers or {})})
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def control(self, key, action, parameters=None, panel_client=PANEL_A):
        status, data = self.post("control", {"application_id": key, "panel_client": panel_client,
                                             "action": action, "parameters": parameters or {}})
        self.assertEqual(status, 200, data)
        return json.loads(data)

    def exchange(self, key, kind, client="a"*32, sequence=1, data=""):
        return self.post("exchange", {"application_id": key, "channel": kind,
                                     "client": client, "sequence": sequence, "data": data})

    def create(self, key, panel_client=PANEL_A):
        return self.registry.get_panel(key, panel_client, create=True, peer=key)

    def test_two_ids_two_channels_and_reconnect_do_not_reset_pause(self):
        a, b = self.create("alpha"), self.create("bravo")
        for key, altitude, heading, count in (("alpha", 1500, 90, 2), ("bravo", 3500, 270, 5)):
            self.control(key, "manual-mode", {"phase": "straight", "speed_kmh": 100,
                         "baro_altitude_m": altitude, "heading_deg": heading,
                         "climb_min_ms": 0, "climb_max_ms": 0})
            self.control(key, "traffic", {"enabled": True, "contact_count": count})
            self.control(key, "start")
        time.sleep(0.2)
        with concurrent.futures.ThreadPoolExecutor() as pool:
            results = list(pool.map(lambda args: self.exchange(*args),
                                    [(key, kind) for key in ("alpha", "bravo") for kind in ("vario", "flarm")]))
        self.assertTrue(all(status == 200 and data.startswith(b"OK\n") for status, data in results))
        sa, sb = self.control("alpha", "state"), self.control("bravo", "state")
        self.assertAlmostEqual(sa["snapshot"]["ownship"]["gps_altitude_m"], 1500, delta=5)
        self.assertAlmostEqual(sb["snapshot"]["ownship"]["gps_altitude_m"], 3500, delta=5)
        self.assertEqual(len(sa["snapshot"]["traffic"]), 2)
        self.assertEqual(len(sb["snapshot"]["traffic"]), 5)
        self.assertEqual(sa["devices"], {"vario": True, "flarm": True})
        self.control("alpha", "pause")
        before = a.runtime.get_snapshot()
        self.assertEqual(self.exchange("alpha", "vario", client="b"*32)[0], 200)
        self.assertEqual(a.runtime.get_snapshot().runtime_state, RuntimeState.PAUSED)
        self.assertEqual(a.runtime.get_snapshot().sim_time_s, before.sim_time_s)
        self.assertEqual(b.runtime.get_snapshot().runtime_state, RuntimeState.RUNNING)
        status, data = self.post("session", {"application_id": "alpha", "panel_client": PANEL_A})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["session_id"], a.runtime.runtime_config.session_id)

    def test_active_application_id_rejects_a_different_panel(self):
        status, data = self.post("session", {"application_id": "alpha", "panel_client": PANEL_A})
        self.assertEqual(status, 200, data)
        session_id = json.loads(data)["session_id"]

        status, data = self.post("session", {"application_id": "alpha", "panel_client": PANEL_B})
        self.assertEqual(status, 409)
        self.assertIn("Podaj inny Application ID", json.loads(data)["error"])
        self.assertEqual(
            self.post("control", {"application_id": "alpha", "panel_client": PANEL_B,
                                  "action": "state", "parameters": {}})[0],
            409,
        )
        status, data = self.post("session", {"application_id": "alpha", "panel_client": PANEL_A})
        self.assertEqual(status, 200, data)
        self.assertEqual(json.loads(data)["session_id"], session_id)

    def test_waiting_before_panel_invalid_ids_private_routes_and_limits(self):
        self.assertEqual(self.exchange("missing", "vario")[0], 404)
        self.assertFalse(self.registry.sessions)
        for key in ("", "x"*65, "a/b", "a\nb", "a\"b"):
            self.assertEqual(self.post("session", {"application_id": key, "panel_client": PANEL_A})[0], 400)
        self.assertEqual(self.post("session", {"application_id": "valid"})[0], 400)
        self.create("alpha")
        self.assertEqual(self.post("control", {"application_id": "alpha", "panel_client": PANEL_A,
                                               "action": "../bridges/start"})[0], 400)
        self.assertEqual(self.post("session", {"application_id": "alpha", "panel_client": PANEL_A},
                                   {"Origin": "https://untrusted.example"})[0], 403)
        self.assertEqual(self.post("control", {"application_id": "alpha", "panel_client": PANEL_A,
                                               "action": "traffic",
                                             "parameters": {"contact_count": 1000000}})[0], 400)
        self.create("bravo")
        self.create("charlie")
        self.assertEqual(self.post("session", {"application_id": "delta", "panel_client": PANEL_A})[0], 503)

    def test_exchange_retry_sequence_validation_and_expiry(self):
        session = self.create("alpha")
        self.control("alpha", "manual-mode", {"phase": "straight", "speed_kmh": 100})
        self.control("alpha", "start")
        first = self.exchange("alpha", "vario")
        self.assertEqual(first, self.exchange("alpha", "vario"))
        self.assertEqual(self.exchange("alpha", "vario", data="41")[0], 409)
        self.assertEqual(self.exchange("alpha", "vario", sequence=3)[0], 409)
        self.registry.expire(session.touched + 901)
        self.assertFalse(self.registry.sessions)
        self.assertEqual(self.exchange("alpha", "vario", sequence=2)[0], 404)

    def test_page_close_ends_only_the_matching_session(self):
        session = self.create("alpha")
        token = session.runtime.runtime_config.session_id
        self.assertEqual(
            self.post("close", {"application_id": "alpha", "session_id": "0" * 32,
                                "panel_client": PANEL_A}),
            (200, b'{"closed": false}'),
        )
        self.assertIn("alpha", self.registry.sessions)

        self.assertEqual(
            self.post("close", {"application_id": "alpha", "session_id": token,
                                "panel_client": PANEL_B})[0],
            409,
        )
        self.assertIn("alpha", self.registry.sessions)

        status, data = self.post("close", {"application_id": "alpha", "session_id": token,
                                           "panel_client": PANEL_A})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data), {"closed": True})
        self.assertNotIn("alpha", self.registry.sessions)
        self.assertFalse(session.runtime.started)
        self.assertEqual(
            self.post("close", {"application_id": "alpha", "session_id": token,
                                "panel_client": PANEL_A})[0],
            200,
        )

    def test_frontend_closes_session_when_its_page_is_closed(self):
        frontend = Path("kigo_xcvario_simulator/online_frontend/app.js").read_text()
        style = Path("kigo_xcvario_simulator/online_frontend/style.css").read_text()
        self.assertIn('navigator.sendBeacon("/simulator/api/close"', frontend)
        self.assertIn('sessionStorage.getItem(storageKey)', frontend)
        self.assertIn('crypto.getRandomValues(new Uint8Array(16))', frontend)
        self.assertIn('panel_client: panelClient', frontend)
        self.assertIn('response.status === 409 && path === "session"', frontend)
        self.assertIn('idInUse:"Ten Application ID jest już używany.', frontend)
        self.assertIn("#status.error{margin-top:12px", style)
        self.assertIn('window.addEventListener("pagehide"', frontend)
        self.assertIn("if (!event.persisted) closeSession();", frontend)
        self.assertIn('event.data.type === "kigo-simulator-close"', frontend)
        self.assertIn('event.origin !== "https://kigoconcept.pl"', frontend)
        self.assertIn('event.origin !== "https://www.kigoconcept.pl"', frontend)
        self.assertIn('idInput.addEventListener("input", () => {\n  closeSession();', frontend)

    def test_failed_connection_retry_does_not_duplicate_arbitrary_binary_writes(self):
        peer, client = socket.socketpair()
        self.addCleanup(peer.close)
        with patch("socket.create_connection", return_value=client):
            channel = Channel(0)
        self.addCleanup(channel.close)
        sent = bytes(range(256))
        peer.sendall(sent)
        first = channel.exchange(1, sent)
        self.assertEqual(peer.recv(256), sent)
        self.assertEqual(bytes.fromhex(first[3:]), sent)
        self.assertEqual(channel.exchange(1, sent), first)
        peer.settimeout(0.05)
        with self.assertRaises(socket.timeout):
            peer.recv(1)
        with self.assertRaises(ApiError):
            channel.exchange(1, b"different")

    def test_online_logger_never_loads_real_flights_and_is_shared_only_within_session(self):
        with patch("kigo_xcvario_simulator.flarm_passthrough.load_default_igc_records",
                   side_effect=AssertionError("Must not load operator flights")):
            a, b = self.create("alpha"), self.create("bravo")
        self.assertEqual(a.runtime.flarm_adapter.flarm_record_names, ("synthetic.igc",))
        self.assertIs(a.runtime.xcvario_adapter._flarm_passthrough, a.runtime.flarm_adapter._flarm_passthrough)
        self.assertIsNot(a.runtime.flarm_adapter._flarm_passthrough, b.runtime.flarm_adapter._flarm_passthrough)


if __name__ == "__main__":
    unittest.main()
