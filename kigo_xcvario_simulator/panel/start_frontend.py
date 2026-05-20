"""Static frontend server for the simulator operator panel."""

from __future__ import annotations

import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DEFAULT_FRONTEND_HOST = "127.0.0.1"
DEFAULT_FRONTEND_PORT = 8180
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"


class NoCacheRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def build_frontend_server(
    *,
    host: str = DEFAULT_FRONTEND_HOST,
    port: int = DEFAULT_FRONTEND_PORT,
) -> ThreadingHTTPServer:
    handler = functools.partial(NoCacheRequestHandler, directory=str(FRONTEND_DIR))
    return ThreadingHTTPServer((host, int(port)), handler)


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
