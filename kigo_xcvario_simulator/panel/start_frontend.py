"""Static frontend server for the simulator operator panel."""

from __future__ import annotations

import argparse
import functools
import json
import os
import shlex
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


DEFAULT_FRONTEND_HOST = "127.0.0.1"
DEFAULT_FRONTEND_PORT = 8180
DEFAULT_CPU_LOG_LIMIT = 7200
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
CPU_LOG_TARGET = "admin@192.168.0.114"
CPU_LOG_IDENTITY = "/Users/slawekpiela/.ssh/kigo_pi"
CPU_LOG_PATH = "/home/admin/kigo_nav/logs/CPU_temperature"


class NoCacheRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/v1/pi/cpu-temperature-log":
            self._handle_cpu_temperature_log(parsed.query)
            return
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def _handle_cpu_temperature_log(self, query: str) -> None:
        limit = _cpu_log_limit(query)
        try:
            payload = _cpu_temperature_payload(limit)
        except Exception as exc:
            self._write_json(502, {"error": "cpu_log_unavailable", "message": str(exc)})
            return
        self._write_json(200, payload)

    def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
        response = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def build_frontend_server(
    *,
    host: str = DEFAULT_FRONTEND_HOST,
    port: int = DEFAULT_FRONTEND_PORT,
) -> ThreadingHTTPServer:
    handler = functools.partial(NoCacheRequestHandler, directory=str(FRONTEND_DIR))
    return ThreadingHTTPServer((host, int(port)), handler)


def _cpu_log_limit(query: str) -> int:
    raw_limit = parse_qs(query).get("limit", [str(DEFAULT_CPU_LOG_LIMIT)])[0]
    try:
        limit = int(raw_limit)
    except ValueError:
        return DEFAULT_CPU_LOG_LIMIT
    return min(max(limit, 1), 50000)


def _cpu_temperature_payload(limit: int) -> dict[str, object]:
    lines = _read_cpu_log_lines(limit)
    records = _parse_cpu_log_lines(lines)
    return {
        "source": {
            "target": os.environ.get("KIGO_CPU_LOG_TARGET", CPU_LOG_TARGET),
            "path": os.environ.get("KIGO_CPU_LOG_PATH", CPU_LOG_PATH),
            "limit": limit,
            "raw_lines": len(lines),
        },
        "records": records,
        "summary": _cpu_log_summary(records),
    }


def _read_cpu_log_lines(limit: int) -> list[str]:
    local_file = os.environ.get("KIGO_CPU_LOG_LOCAL_FILE")
    if local_file:
        return Path(local_file).read_text(encoding="utf-8").splitlines()[-limit:]

    target = os.environ.get("KIGO_CPU_LOG_TARGET", CPU_LOG_TARGET)
    identity = os.environ.get("KIGO_CPU_LOG_IDENTITY", CPU_LOG_IDENTITY)
    log_path = os.environ.get("KIGO_CPU_LOG_PATH", CPU_LOG_PATH)
    timeout_s = float(os.environ.get("KIGO_CPU_LOG_SSH_TIMEOUT_SECONDS", "8"))

    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "IdentitiesOnly=yes",
    ]
    if identity:
        command.extend(["-i", identity])
    command.extend([target, f"tail -n {int(limit)} {shlex.quote(log_path)}"])

    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"ssh returned {result.returncode}"
        raise RuntimeError(message)
    return result.stdout.splitlines()


def _parse_cpu_log_lines(lines: list[str]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        values = {}
        for part in parts[1:]:
            key, separator, value = part.partition("=")
            if separator:
                values[key] = value
        temp_c = _optional_float(values.get("cpu_temp_c"))
        cpu_percent = _optional_float(values.get("cpu_used_percent"))
        if temp_c is None and cpu_percent is None:
            continue
        records.append(
            {
                "timestamp": parts[0],
                "cpu_temp_c": temp_c,
                "cpu_used_percent": cpu_percent,
            }
        )
    return records


def _optional_float(value: str | None) -> float | None:
    if value in (None, "", "NA"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _cpu_log_summary(records: list[dict[str, object]]) -> dict[str, object]:
    temps = [float(record["cpu_temp_c"]) for record in records if record.get("cpu_temp_c") is not None]
    cpus = [float(record["cpu_used_percent"]) for record in records if record.get("cpu_used_percent") is not None]
    return {
        "sample_count": len(records),
        "first_timestamp": records[0]["timestamp"] if records else None,
        "last_timestamp": records[-1]["timestamp"] if records else None,
        "temperature_c": _series_summary(temps),
        "cpu_percent": _series_summary(cpus),
    }


def _series_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "avg": None, "max": None}
    return {
        "min": min(values),
        "avg": sum(values) / len(values),
        "max": max(values),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the simulator control panel on the local Mac.")
    parser.add_argument("--host", default=DEFAULT_FRONTEND_HOST, help="Bind host for the local panel server.")
    parser.add_argument("--port", type=int, default=DEFAULT_FRONTEND_PORT, help="Bind port for the local panel server.")
    args = parser.parse_args(argv)

    server = build_frontend_server(host=args.host, port=args.port)
    try:
        print(f"Simulator panel: http://{args.host}:{args.port}/")
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
