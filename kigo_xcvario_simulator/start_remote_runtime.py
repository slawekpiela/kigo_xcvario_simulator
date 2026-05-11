"""CLI entrypoint for running the remote simulator runtime on Pi or VM."""

from __future__ import annotations

import argparse
from pathlib import Path
import signal
import sys
import time

if __package__ in {None, ""}:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from kigo_xcvario_simulator.config import load_runtime_config
    from kigo_xcvario_simulator.control_api import ControlApiServer
    from kigo_xcvario_simulator.session import SimulatorRuntimeSession
else:
    from .config import load_runtime_config
from .control_api import ControlApiServer
from .session import SimulatorRuntimeSession


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "examples" / "runtime.example.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the XCvario simulator runtime.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to the runtime JSON config.",
    )
    args = parser.parse_args(argv)

    runtime_config = load_runtime_config(args.config)
    session = SimulatorRuntimeSession(runtime_config)
    control_api = ControlApiServer(
        bind_host=runtime_config.control_api.bind_host,
        port=runtime_config.control_api.port,
        token=runtime_config.control_api.token,
        session=session,
        cors_allowed_origins=runtime_config.control_api.cors_allowed_origins,
    )

    stop_requested = False

    def _request_stop(_signum, _frame) -> None:
        nonlocal stop_requested
        stop_requested = True

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, _request_stop)

    session.start()
    control_api.start()
    try:
        while not stop_requested:
            time.sleep(0.25)
    finally:
        control_api.stop()
        session.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
