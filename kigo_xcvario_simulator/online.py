"""Session-isolated Internet facade. Bind to loopback behind an HTTPS proxy.

Application ID selects a simulator session and is reserved by one browser panel
at a time; it is not account authentication. The facade never publishes the lab
bridge administration API.
Device transport uses bounded HTTPS exchanges, preserving arbitrary wire bytes.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import math
from pathlib import Path
import re
import secrets
import select
import signal
import socket
import threading
import time
from urllib.parse import urlsplit

from .config import load_runtime_config
from .control_api import ControlApiServer
from .session import SimulatorRuntimeSession
from .flarm_passthrough import FlarmPassthroughSimulator

PREFIX = "/simulator"
MAX_BODY = 40000
MAX_BYTES = 16384
ID_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
TOKEN_PATTERN = re.compile(r"[a-f0-9]{32}\Z")
CONTROL_PATHS = frozenset(("start", "pause", "reset", "preset", "manual-mode", "traffic",
                           "wind", "oat", "altimeter", "start-airport"))
PARAMETERS = {
    "state": (), "start": (), "pause": (), "reset": (),
    "preset": ("preset_id", "seed", "autostart"),
    "manual-mode": ("phase", "speed_kmh", "heading_deg", "baro_altitude_m", "turn_radius_m",
                    "climb_min_ms", "climb_max_ms", "on_ground"),
    "traffic": ("enabled", "contact_count", "collision_course", "motion_mode", "reset"),
    "wind": ("direction_deg", "speed_kmh"), "oat": ("oat_c",),
    "altimeter": ("qnh_hpa",), "start-airport": ("icao",),
}
FRONTEND = Path(__file__).with_name("online_frontend")


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def application_id(value):
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ApiError(400, "Application ID: use 1–64 letters, digits, dot, underscore or dash.")
    return value


def panel_client(value):
    if not isinstance(value, str) or not TOKEN_PATTERN.fullmatch(value):
        raise ApiError(400, "Invalid panel client ID.")
    return value


class Channel:
    """One persistent device socket; retrying an exchange never replays commands."""
    def __init__(self, port):
        self.socket = socket.create_connection(("127.0.0.1", port), timeout=2)
        self.socket.settimeout(2)
        self.lock = threading.Lock()
        self.sequence = 0
        self.previous_request = None
        self.previous_response = None
        self.touched = time.monotonic()

    def exchange(self, sequence, outgoing):
        with self.lock:
            self.touched = time.monotonic()
            if sequence == self.sequence and self.previous_response is not None:
                if outgoing != self.previous_request:
                    raise ApiError(409, "Sequence reused with different data.")
                return self.previous_response
            if sequence != self.sequence + 1:
                raise ApiError(409, "Device connection expired; reconnect.")
            if outgoing:
                self.socket.sendall(outgoing)
            received = b""
            if select.select([self.socket], [], [], 0.2)[0]:
                received = self.socket.recv(MAX_BYTES)
                if not received:
                    raise ApiError(410, "Device connection closed; reconnect.")
            self.sequence = sequence
            self.previous_request = outgoing
            self.previous_response = "OK\n" + received.hex()
            return self.previous_response

    def close(self):
        with self.lock:
            self.socket.close()


class OnlineSession:
    def __init__(self, config, panel_client_id):
        config = replace(config, session_id=secrets.token_hex(16),
                         xcvario=replace(config.xcvario, bind_host="127.0.0.1", port=0),
                         flarm=replace(config.flarm, bind_host="127.0.0.1", port=0))
        self.runtime = SimulatorRuntimeSession(config, activate_on_connect=False,
                         flarm_passthrough=FlarmPassthroughSimulator.synthetic())
        self.api = ControlApiServer(bind_host="127.0.0.1", port=0, session=self.runtime)
        self.channels = {}
        self.panel_client = panel_client_id
        self.lock = threading.RLock()
        self.touched = time.monotonic()
        try:
            self.runtime.start()
            self.api.start()
        except BaseException:
            self.api.stop()
            self.runtime.stop()
            raise

    def channel(self, kind, client, sequence):
        key = (kind, client)
        with self.lock:
            self.touched = time.monotonic()
            channel = self.channels.get(key)
            if channel is None:
                if sequence != 1:
                    raise ApiError(409, "Device connection expired; reconnect.")
                if len(self.channels) >= 8:
                    raise ApiError(429, "Too many device connections for this Application ID.")
                adapter = self.runtime.flarm_adapter if kind == "flarm" else self.runtime.xcvario_adapter
                channel = self.channels[key] = Channel(adapter.bound_port)
            return channel

    def expire_channels(self, now):
        with self.lock:
            for key, channel in list(self.channels.items()):
                if now - channel.touched > 30:
                    del self.channels[key]
                    channel.close()

    def close(self):
        with self.lock:
            for channel in self.channels.values():
                channel.close()
            self.channels.clear()
        self.api.stop()
        self.runtime.stop()


class SessionRegistry:
    def __init__(self, config, limit=50, idle_seconds=900):
        self.config, self.limit, self.idle_seconds = config, limit, idle_seconds
        self.sessions = {}
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.creation_times = OrderedDict()
        self.reaper = threading.Thread(target=self._reap, name="sim-session-expiry", daemon=True)
        self.reaper.start()

    def get(self, key):
        key = application_id(key)
        with self.lock:
            session = self.sessions.get(key)
            if session is None:
                raise ApiError(404, "Waiting: open the simulator page and enter this Application ID.")
            session.touched = time.monotonic()
            return session

    def get_panel(self, key, panel_client_id, create=False, peer=""):
        key = application_id(key)
        panel_client_id = panel_client(panel_client_id)
        with self.lock:
            session = self.sessions.get(key)
            if session is None and create:
                if len(self.sessions) >= self.limit:
                    raise ApiError(503, "Simulator busy. Try again later.")
                now = time.monotonic()
                previous = self.creation_times.get(peer, 0)
                if now - previous < 1:
                    raise ApiError(429, "Please wait before creating another session.")
                self.creation_times[peer] = now
                self.creation_times.move_to_end(peer)
                while len(self.creation_times) > 1024:
                    self.creation_times.popitem(last=False)
                session = self.sessions[key] = OnlineSession(self.config, panel_client_id)
            if session is None:
                raise ApiError(404, "Waiting: open the simulator page and enter this Application ID.")
            if not secrets.compare_digest(session.panel_client, panel_client_id):
                raise ApiError(409, "Ten Application ID jest już używany w innym oknie lub przez innego użytkownika. Podaj inny Application ID.")
            session.touched = time.monotonic()
            return session

    def expire(self, now=None):
        now = time.monotonic() if now is None else now
        expired = []
        with self.lock:
            for key, session in list(self.sessions.items()):
                session.expire_channels(now)
                if now - session.touched > self.idle_seconds:
                    expired.append(self.sessions.pop(key))
        for session in expired:
            session.close()

    def close_session(self, key, session_id, panel_client_id):
        key = application_id(key)
        panel_client_id = panel_client(panel_client_id)
        if not isinstance(session_id, str) or not TOKEN_PATTERN.fullmatch(session_id):
            raise ApiError(400, "Invalid session ID.")
        with self.lock:
            session = self.sessions.get(key)
            if session is None:
                return False
            if not secrets.compare_digest(session.panel_client, panel_client_id):
                raise ApiError(409, "Ten Application ID jest używany przez inny panel.")
            if session.runtime.runtime_config.session_id != session_id:
                return False
            del self.sessions[key]
        session.close()
        return True

    def _reap(self):
        while not self.closed.wait(5):
            self.expire()

    def close(self):
        self.closed.set()
        self.reaper.join()
        with self.lock:
            sessions, self.sessions = list(self.sessions.values()), {}
        for session in sessions:
            session.close()


class OnlineServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, address, registry):
        self.registry = registry
        self.slots = threading.BoundedSemaphore(256)
        super().__init__(address, OnlineHandler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class OnlineHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_args):
        # IDs and exchanged protocol bytes must never enter access logs.
        pass

    def reply(self, status, payload, content_type="application/json"):
        if not isinstance(payload, bytes):
            payload = json.dumps(payload).encode() if content_type == "application/json" else payload.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; frame-ancestors https://kigoconcept.pl https://www.kigoconcept.pl; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == PREFIX + "/health":
            self.reply(200, {"status": "ok"})
            return
        filename = {PREFIX: "index.html", PREFIX + "/": "index.html",
                    PREFIX + "/app.js": "app.js", PREFIX + "/style.css": "style.css"}.get(path)
        if filename is None:
            self.reply(404, {"error": "Not found"})
            return
        content_type = {"html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8",
                        "css": "text/css; charset=utf-8"}[filename.rsplit(".", 1)[1]]
        self.reply(200, (FRONTEND / filename).read_bytes(), content_type)

    def do_POST(self):
        try:
            # No cross-origin control of a session through a pilot's browser.
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                raise ApiError(403, "Cross-origin request rejected.")
            if self.headers.get("Transfer-Encoding"):
                raise ApiError(400, "Content-Length required.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise ApiError(413, "Request too large or empty.")
            if self.headers.get_content_type() != "application/json":
                raise ApiError(415, "JSON required.")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ApiError(400, "Incomplete request.")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ApiError(400, "JSON object required.")
            path = urlsplit(self.path).path
            if path not in (PREFIX + "/api/session", PREFIX + "/api/close",
                            PREFIX + "/api/control", PREFIX + "/api/exchange"):
                raise ApiError(404, "Not found")
            if path.endswith("/close"):
                closed = self.server.registry.close_session(
                    payload.get("application_id"), payload.get("session_id"),
                    payload.get("panel_client"))
                self.reply(200, {"closed": closed})
                return
            if path.endswith("/session"):
                session = self.server.registry.get_panel(
                    payload.get("application_id"), payload.get("panel_client"),
                    create=True, peer=self.client_address[0])
                self.reply(200, {"session_id": session.runtime.runtime_config.session_id})
            elif path.endswith("/control"):
                session = self.server.registry.get_panel(
                    payload.get("application_id"), payload.get("panel_client"))
                self.control(session, payload)
            else:
                session = self.server.registry.get(payload.get("application_id"))
                self.exchange(session, payload)
        except ApiError as error:
            self.close_connection = True
            self.reply(error.status, {"error": error.message})
        except (ValueError, TypeError, KeyError, RecursionError):
            self.close_connection = True
            self.reply(400, {"error": "Invalid request."})
        except (OSError, http.client.HTTPException):
            self.close_connection = True
            try:
                self.reply(502, {"error": "Simulator connection interrupted."})
            except OSError:
                pass

    def control(self, session, payload):
        action = payload.get("action")
        if action != "state" and action not in CONTROL_PATHS:
            raise ApiError(400, "Unknown simulation action.")
        params = payload.get("parameters", {})
        if not isinstance(params, dict):
            raise ApiError(400, "Parameters must be an object.")
        if set(params) - set(PARAMETERS[action]):
            raise ApiError(400, "Unsupported simulation parameter.")
        # Bounds apply to the public API too, not only to browser controls.
        for key, value in params.items():
            if isinstance(value, (dict, list)) or (isinstance(value, float) and not math.isfinite(value)):
                raise ApiError(400, "Invalid parameter.")
            if isinstance(value, str) and len(value) > 100:
                raise ApiError(400, "Parameter too long.")
        bounds = {"contact_count": (0, 100), "speed_kmh": (0, 400), "heading_deg": (0, 360),
                  "direction_deg": (0, 360), "baro_altitude_m": (-500, 15000),
                  "qnh_hpa": (800, 1100), "oat_c": (-80, 60), "turn_radius_m": (30, 5000),
                  "climb_min_ms": (-30, 30), "climb_max_ms": (-30, 30), "seed": (0, 2**32 - 1)}
        for key, (low, high) in bounds.items():
            if key in params and (not isinstance(params[key], (float, int)) or not low <= params[key] <= high):
                raise ApiError(400, "Parameter outside supported range: " + key)
        if params.get("climb_min_ms", -30) > params.get("climb_max_ms", 30):
            raise ApiError(400, "Minimum climb exceeds maximum.")
        connection = http.client.HTTPConnection("127.0.0.1", session.api.bound_port, timeout=10)
        try:
            connection.request("GET" if action == "state" else "POST", "/api/v1/simulation/" + action,
                               body=None if action == "state" else json.dumps(params),
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            data = response.read(MAX_BODY)
            if action == "state" and response.status == 200:
                snapshot = json.loads(data)["snapshot"]
                now = time.monotonic()
                with session.lock:
                    devices = {kind: any(k == kind and now - c.touched < 10
                                        for (k, _), c in session.channels.items())
                               for kind in ("vario", "flarm")}
                data = json.dumps({"snapshot": snapshot, "devices": devices}).encode()
            self.reply(200 if response.status == 204 else response.status, data or b"{}")
        finally:
            connection.close()

    def exchange(self, session, payload):
        kind, client = payload.get("channel"), payload.get("client")
        sequence, data = payload.get("sequence"), payload.get("data")
        if kind not in ("vario", "flarm") or not isinstance(client, str) or not TOKEN_PATTERN.fullmatch(client):
            raise ApiError(400, "Invalid channel or client.")
        if type(sequence) is not int or not 1 <= sequence < 2**53:
            raise ApiError(400, "Invalid sequence.")
        if not isinstance(data, str) or len(data) > MAX_BYTES * 2:
            raise ApiError(400, "Invalid device data.")
        outgoing = bytes.fromhex(data)
        channel = session.channel(kind, client, sequence)
        self.reply(200, channel.exchange(sequence, outgoing), "text/plain")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--max-sessions", type=int, default=50)
    parser.add_argument("--idle-seconds", type=int, default=900)
    parser.add_argument("--config", default=str(Path(__file__).with_name("examples") / "runtime.example.json"))
    args = parser.parse_args()
    registry = SessionRegistry(load_runtime_config(args.config), args.max_sessions, args.idle_seconds)
    server = OnlineServer((args.host, args.port), registry)
    def stop(_signum, _frame):
        # shutdown() must run outside the serve_forever thread.
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        registry.close()


if __name__ == "__main__":
    main()
