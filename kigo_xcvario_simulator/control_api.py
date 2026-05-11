"""HTTP/JSON control plane and SSE stream for the simulator runtime."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import json
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .config import CONTROL_TOKEN_HEADER
from .contracts import ManualModeInput, PresetRequest, SimulationSnapshot
from .state import HealthState, FlightPhase


class ControlApiServer:
    def __init__(
        self,
        *,
        bind_host: str,
        port: int,
        token: str,
        session,
        cors_allowed_origins: tuple[str, ...] = (),
    ) -> None:
        self._bind_host = bind_host
        self._requested_port = int(port)
        self._token = token
        self._session = session
        self._cors_allowed_origins = tuple(cors_allowed_origins)
        self._server: ThreadingHTTPServer | None = None
        self._server_thread: Thread | None = None
        self._running = Event()
        self._subscribers: set[Queue[str | None]] = set()
        self._subscriber_lock = Lock()
        self.bound_port = int(port)

    @property
    def session(self):
        return self._session

    def start(self) -> None:
        if self._server is not None:
            return
        server = ThreadingHTTPServer((self._bind_host, self._requested_port), self._build_handler())
        self._server = server
        self.bound_port = int(server.server_address[1])
        self._running.set()
        self._session.add_snapshot_listener(self.publish_snapshot)
        self._server_thread = Thread(target=server.serve_forever, name="sim-control-api", daemon=True)
        self._server_thread.start()

    def stop(self) -> None:
        self._running.clear()
        self._session.remove_snapshot_listener(self.publish_snapshot)
        with self._subscriber_lock:
            subscribers = list(self._subscribers)
            self._subscribers.clear()
        for subscriber in subscribers:
            self._offer_to_subscriber(subscriber, None)
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._server_thread is not None:
            self._server_thread.join(timeout=2.0)
            self._server_thread = None

    def publish_snapshot(self, snapshot: SimulationSnapshot) -> None:
        payload = self._build_sse_payload(snapshot)
        with self._subscriber_lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            self._offer_to_subscriber(subscriber, payload)

    def _offer_to_subscriber(self, subscriber: Queue[str | None], payload: str | None) -> None:
        try:
            subscriber.put_nowait(payload)
        except Full:
            try:
                subscriber.get_nowait()
            except Empty:
                pass
            try:
                subscriber.put_nowait(payload)
            except Full:
                return

    def _build_handler(self):
        controller = self

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self._write_cors_headers()
                self.end_headers()

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/api/v1/health/live":
                    self._write_json(200, {"status": "live"})
                    return
                if parsed.path == "/api/v1/health/ready":
                    status_code = 200 if controller.session.started else 503
                    self._write_json(status_code, {"status": "ready" if status_code == 200 else "starting"})
                    return
                if parsed.path == "/api/v1/simulation/state":
                    if not self._require_token():
                        return
                    self._write_json(200, controller._state_payload())
                    return
                if parsed.path == "/api/v1/events":
                    if not self._require_token():
                        return
                    self._stream_events()
                    return
                self._write_json(404, {"error": "not_found"})

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if not self._require_token():
                    return
                try:
                    handled = self._handle_post(parsed.path)
                except KeyError as exc:
                    self._write_json(400, {"error": "bad_request", "message": f"missing field: {exc.args[0]}"})
                    return
                except ValueError as exc:
                    self._write_json(400, {"error": "bad_request", "message": str(exc)})
                    return
                if handled:
                    return
                self._write_json(404, {"error": "not_found"})

            def _handle_post(self, path: str) -> bool:
                if path == "/api/v1/simulation/start":
                    controller.session.start_simulation()
                    self.send_response(204)
                    self._write_cors_headers()
                    self.end_headers()
                    return True
                if path == "/api/v1/simulation/pause":
                    controller.session.pause_simulation()
                    self.send_response(204)
                    self._write_cors_headers()
                    self.end_headers()
                    return True
                if path == "/api/v1/simulation/reset":
                    controller.session.reset_simulation()
                    self.send_response(204)
                    self._write_cors_headers()
                    self.end_headers()
                    return True
                if path == "/api/v1/simulation/preset":
                    payload = self._read_json_body()
                    request = PresetRequest(
                        preset_id=str(payload["preset_id"]),
                        seed=int(payload["seed"]),
                        autostart=bool(payload.get("autostart", True)),
                    )
                    overrides = payload.get("overrides")
                    controller.session.load_preset(request, overrides=overrides if isinstance(overrides, dict) else None)
                    self.send_response(204)
                    self._write_cors_headers()
                    self.end_headers()
                    return True
                if path == "/api/v1/simulation/manual-mode":
                    payload = self._read_json_body()
                    phase_token = str(payload["phase"])
                    manual = ManualModeInput(
                        phase=FlightPhase.GLIDER_LAUNCH if phase_token == "on_ground" else FlightPhase(phase_token),
                        heading_deg=_optional_float(payload.get("heading_deg")),
                        speed_kmh=_optional_float(payload.get("speed_kmh")),
                        baro_altitude_m=_optional_float_any(payload, "wysokosc", "baro_altitude_m", "altitude_m"),
                        speed_min_kmh=_optional_float(payload.get("speed_min_kmh")),
                        speed_max_kmh=_optional_float(payload.get("speed_max_kmh")),
                        turn_radius_m=_optional_float(payload.get("turn_radius_m")),
                        climb_min_ms=_optional_float(payload.get("climb_min_ms")),
                        climb_max_ms=_optional_float(payload.get("climb_max_ms")),
                        sink_ms=_optional_float(payload.get("sink_ms")),
                        on_ground=phase_token == "on_ground" or bool(payload.get("on_ground", False)),
                    )
                    controller.session.set_manual_mode(manual)
                    self.send_response(204)
                    self._write_cors_headers()
                    self.end_headers()
                    return True
                if path == "/api/v1/simulation/traffic":
                    payload = self._read_json_body()
                    controller.session.set_traffic_config(
                        bool(payload.get("enabled", True)),
                        int(payload.get("contact_count", 0)),
                        bool(payload.get("collision_course", False)),
                    )
                    self.send_response(204)
                    self._write_cors_headers()
                    self.end_headers()
                    return True
                if path == "/api/v1/simulation/wind":
                    payload = self._read_json_body()
                    controller.session.set_wind(
                        _required_float_any(payload, "direction_deg", "wind_direction_deg", "kierunek"),
                        _required_float_any(payload, "speed_kmh", "wind_speed_kmh", "sila"),
                    )
                    self.send_response(204)
                    self._write_cors_headers()
                    self.end_headers()
                    return True
                if path == "/api/v1/simulation/oat":
                    payload = self._read_json_body()
                    controller.session.set_oat_c(_required_float_any(payload, "oat_c", "temperature_c", "oat"))
                    self.send_response(204)
                    self._write_cors_headers()
                    self.end_headers()
                    return True
                return False

            def _stream_events(self) -> None:
                subscriber: Queue[str | None] = Queue(maxsize=1)
                with controller._subscriber_lock:
                    controller._subscribers.add(subscriber)
                controller._offer_to_subscriber(subscriber, controller._build_sse_payload(controller.session.get_snapshot()))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self._write_cors_headers()
                self.end_headers()
                try:
                    while controller._running.is_set():
                        try:
                            payload = subscriber.get(timeout=0.5)
                        except Empty:
                            payload = ": keepalive\n\n"
                        if payload is None:
                            break
                        self.wfile.write(payload.encode("utf-8"))
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return
                finally:
                    with controller._subscriber_lock:
                        controller._subscribers.discard(subscriber)

            def _read_json_body(self) -> dict[str, object]:
                content_length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    raise ValueError("invalid_json") from exc
                if not isinstance(parsed, dict):
                    raise ValueError("invalid_json")
                return parsed

            def _require_token(self) -> bool:
                if self.headers.get(CONTROL_TOKEN_HEADER) == controller._token:
                    return True
                self._write_json(401, {"error": "unauthorized"})
                return False

            def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
                response = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self._write_cors_headers()
                self.end_headers()
                self.wfile.write(response)

            def _write_cors_headers(self) -> None:
                origin = self.headers.get("Origin")
                if origin and origin in controller._cors_allowed_origins:
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Access-Control-Allow-Headers", f"Content-Type, {CONTROL_TOKEN_HEADER}")
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

            def log_message(self, format: str, *args) -> None:
                return None

        return Handler

    def _state_payload(self) -> dict[str, object]:
        return {
            "snapshot": _to_jsonable(self._session.get_snapshot()),
            "runtime": self._session.get_runtime_metadata(),
        }

    def _build_sse_payload(self, snapshot: SimulationSnapshot) -> str:
        events = [
            ("state", self._state_payload()),
            ("ownship", _to_jsonable(snapshot.ownship)),
            ("traffic", _to_jsonable(snapshot.traffic)),
            (
                "health",
                {
                    "health": snapshot.health.value,
                    "runtime_state": snapshot.runtime_state.value,
                    "sim_time_s": snapshot.sim_time_s,
                },
            ),
        ]
        chunks = []
        for name, payload in events:
            chunks.append(f"event: {name}\n")
            chunks.append(f"data: {json.dumps(payload, separators=(',', ':'), ensure_ascii=True)}\n\n")
        return "".join(chunks)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_float_any(payload: dict[str, object], *keys: str) -> float | None:
    for key in keys:
        if key in payload:
            return _optional_float(payload.get(key))
    return None


def _required_float_any(payload: dict[str, object], *keys: str) -> float:
    for key in keys:
        if key in payload:
            return float(payload[key])
    raise KeyError(keys[0])


def _to_jsonable(value: object):
    if is_dataclass(value):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value
