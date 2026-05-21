"""SSH-backed control for simulator TCP-to-PTY bridges on remote hosts."""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
import subprocess
import time
from typing import Any


PRIMARY_UNIT = "kigo-xcvario-pty-xcvario.service"
FLARM_UNIT = "kigo-xcvario-pty-flarm.service"
PRIMARY_UNIT_NAME = PRIMARY_UNIT.removesuffix(".service")
FLARM_UNIT_NAME = FLARM_UNIT.removesuffix(".service")
DEFAULT_PRIMARY_SERIAL_PATH = "/tmp/kigo-sim/xcvario"
DEFAULT_FLARM_SERIAL_PATH = "/tmp/kigo-sim/flarm"
DEFAULT_READY_TIMEOUT_S = 8.0
STATUS_POLL_INTERVAL_S = 0.5


@dataclass(frozen=True)
class BridgeNode:
    node_id: str
    ssh_target: str
    simulator_host: str
    workdir: str
    identity_file: str = ""
    primary_serial_path: str = DEFAULT_PRIMARY_SERIAL_PATH
    flarm_serial_path: str = DEFAULT_FLARM_SERIAL_PATH


class BridgeControl:
    def status(self, payload: dict[str, object]) -> dict[str, object]:
        config = _parse_payload(payload)
        return _result_payload("status", [_node_status(node) for node in config.nodes])

    def start(self, payload: dict[str, object]) -> dict[str, object]:
        config = _parse_payload(payload)
        results = []
        for node in config.nodes:
            command = _start_script(node, config.primary_port, config.flarm_port)
            run = _run_remote(node, command)
            status = _wait_node_status(node, want_ready=True, timeout_s=config.ready_timeout_s)
            status["action_returncode"] = run.returncode
            status["action_stdout"] = run.stdout.strip()
            status["action_stderr"] = run.stderr.strip()
            results.append(status)
        return _result_payload("start", results)

    def stop(self, payload: dict[str, object]) -> dict[str, object]:
        config = _parse_payload(payload)
        results = []
        for node in config.nodes:
            run = _run_remote(node, _stop_script(node))
            status = _wait_node_status(node, want_ready=False, timeout_s=min(3.0, config.ready_timeout_s))
            status["action_returncode"] = run.returncode
            status["action_stdout"] = run.stdout.strip()
            status["action_stderr"] = run.stderr.strip()
            results.append(status)
        return _result_payload("stop", results)

    def restart(self, payload: dict[str, object]) -> dict[str, object]:
        self.stop(payload)
        return self.start(payload)


@dataclass(frozen=True)
class _BridgeConfig:
    nodes: tuple[BridgeNode, ...]
    primary_port: int
    flarm_port: int
    ready_timeout_s: float


def _parse_payload(payload: dict[str, object]) -> _BridgeConfig:
    nodes_raw = payload.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        raise ValueError("bridges.nodes must be a non-empty list.")
    if len(nodes_raw) > 6:
        raise ValueError("bridges.nodes must contain at most 6 nodes.")
    nodes = tuple(_parse_node(node_raw) for node_raw in nodes_raw)
    return _BridgeConfig(
        nodes=nodes,
        primary_port=_port(payload.get("primary_port"), default=4353),
        flarm_port=_port(payload.get("flarm_port"), default=4354),
        ready_timeout_s=_positive_float(payload.get("ready_timeout_s"), default=DEFAULT_READY_TIMEOUT_S),
    )


def _parse_node(node_raw: object) -> BridgeNode:
    if not isinstance(node_raw, dict):
        raise ValueError("bridge node must be an object.")
    node_id = _text(node_raw.get("id"), default="bridge")
    ssh_target = _required_text(node_raw.get("ssh_target"), "bridge ssh_target")
    simulator_host = _required_text(node_raw.get("simulator_host"), "bridge simulator_host")
    workdir = _required_text(node_raw.get("workdir"), "bridge workdir")
    return BridgeNode(
        node_id=node_id,
        ssh_target=ssh_target,
        simulator_host=simulator_host,
        workdir=workdir,
        identity_file=_text(node_raw.get("identity_file"), default=""),
        primary_serial_path=_text(node_raw.get("primary_serial_path"), default=DEFAULT_PRIMARY_SERIAL_PATH),
        flarm_serial_path=_text(node_raw.get("flarm_serial_path"), default=DEFAULT_FLARM_SERIAL_PATH),
    )


def _node_status(node: BridgeNode) -> dict[str, object]:
    run = _run_remote(node, _status_script(node))
    parsed = _parse_status(run.stdout)
    primary_status_payload = _parse_status_json(parsed.get("primary_status_json", ""))
    flarm_status_payload = _parse_status_json(parsed.get("flarm_status_json", ""))
    primary_active = parsed.get("primary") == "active"
    flarm_active = parsed.get("flarm") == "active"
    primary_pty_exists = parsed.get("primary_pty_exists") == "true"
    flarm_pty_exists = parsed.get("flarm_pty_exists") == "true"
    primary_tcp_connected = bool(primary_status_payload.get("tcp_connected"))
    flarm_tcp_connected = bool(flarm_status_payload.get("tcp_connected"))
    primary_ready = primary_active and primary_pty_exists and primary_tcp_connected
    flarm_ready = flarm_active and flarm_pty_exists and flarm_tcp_connected
    return {
        "id": node.node_id,
        "ssh_target": node.ssh_target,
        "simulator_host": node.simulator_host,
        "workdir": node.workdir,
        "ready": primary_ready and flarm_ready,
        "primary_ready": primary_ready,
        "flarm_ready": flarm_ready,
        "primary_active": primary_active,
        "flarm_active": flarm_active,
        "primary_status": parsed.get("primary", "unknown"),
        "flarm_status": parsed.get("flarm", "unknown"),
        "primary_serial_path": node.primary_serial_path,
        "flarm_serial_path": node.flarm_serial_path,
        "primary_pty_exists": primary_pty_exists,
        "flarm_pty_exists": flarm_pty_exists,
        "primary_pty_target": parsed.get("primary_pty_target", ""),
        "flarm_pty_target": parsed.get("flarm_pty_target", ""),
        "primary_tcp_connected": primary_tcp_connected,
        "flarm_tcp_connected": flarm_tcp_connected,
        "primary_last_error": str(primary_status_payload.get("last_connect_error", "")),
        "flarm_last_error": str(flarm_status_payload.get("last_connect_error", "")),
        "primary_bytes_tcp_to_pty": int(primary_status_payload.get("bytes_tcp_to_pty") or 0),
        "primary_bytes_pty_to_tcp": int(primary_status_payload.get("bytes_pty_to_tcp") or 0),
        "flarm_bytes_tcp_to_pty": int(flarm_status_payload.get("bytes_tcp_to_pty") or 0),
        "flarm_bytes_pty_to_tcp": int(flarm_status_payload.get("bytes_pty_to_tcp") or 0),
        "primary_bridge_status": primary_status_payload,
        "flarm_bridge_status": flarm_status_payload,
        "processes": parsed.get("processes", ""),
        "returncode": run.returncode,
        "stdout": run.stdout.strip(),
        "stderr": run.stderr.strip(),
    }


def _wait_node_status(node: BridgeNode, *, want_ready: bool, timeout_s: float) -> dict[str, object]:
    deadline_s = time.monotonic() + max(0.0, timeout_s)
    status = _node_status(node)
    while time.monotonic() < deadline_s:
        if want_ready and bool(status.get("ready")):
            return status
        if not want_ready and not (bool(status.get("primary_active")) or bool(status.get("flarm_active"))):
            return status
        time.sleep(STATUS_POLL_INTERVAL_S)
        status = _node_status(node)
    status["ready_wait_timed_out"] = want_ready and not bool(status.get("ready"))
    status["stop_wait_timed_out"] = not want_ready and (
        bool(status.get("primary_active")) or bool(status.get("flarm_active"))
    )
    return status


def _run_remote(node: BridgeNode, script: str) -> subprocess.CompletedProcess[str]:
    if _is_local_target(node.ssh_target):
        command = ["bash", "-lc", script]
        try:
            return subprocess.run(command, text=True, capture_output=True, timeout=14, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return subprocess.CompletedProcess(command, 255, "", str(exc))

    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=6",
    ]
    if node.identity_file:
        command.extend(["-i", node.identity_file])
    command.extend([node.ssh_target, f"bash -lc {_shell_quote(script)}"])
    try:
        return subprocess.run(command, text=True, capture_output=True, timeout=14, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(command, 255, "", str(exc))


def _is_local_target(ssh_target: str) -> bool:
    host = _ssh_target_host(ssh_target).casefold()
    return host in _local_target_names()


def _ssh_target_host(ssh_target: str) -> str:
    value = ssh_target.strip()
    if "@" in value:
        value = value.rsplit("@", 1)[1]
    if value.startswith("[") and "]" in value:
        return value[1 : value.index("]")]
    return value.split(":", 1)[0]


def _local_target_names() -> set[str]:
    names = {"", "local", "localhost", "127.0.0.1", "::1", "0.0.0.0"}
    for name in (socket.gethostname(), socket.getfqdn()):
        if name:
            names.add(name.casefold())
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            names.add(str(info[4][0]).casefold())
    except OSError:
        pass
    try:
        run = subprocess.run(["hostname", "-I"], text=True, capture_output=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return names
    for address in run.stdout.split():
        names.add(address.casefold())
    return names


def _status_script(node: BridgeNode) -> str:
    return (
        f"printf 'primary=%s\\n' \"$(systemctl --user is-active {PRIMARY_UNIT} 2>/dev/null || true)\"\n"
        f"printf 'flarm=%s\\n' \"$(systemctl --user is-active {FLARM_UNIT} 2>/dev/null || true)\"\n"
        f"printf 'primary_pty_exists=%s\\n' \"$([ -e {_shell_quote(node.primary_serial_path)} ] || [ -L {_shell_quote(node.primary_serial_path)} ]; echo $?)\" | sed 's/=0/=true/;s/=1/=false/'\n"
        f"printf 'flarm_pty_exists=%s\\n' \"$([ -e {_shell_quote(node.flarm_serial_path)} ] || [ -L {_shell_quote(node.flarm_serial_path)} ]; echo $?)\" | sed 's/=0/=true/;s/=1/=false/'\n"
        f"printf 'primary_pty_target=%s\\n' \"$(readlink {_shell_quote(node.primary_serial_path)} 2>/dev/null || true)\"\n"
        f"printf 'flarm_pty_target=%s\\n' \"$(readlink {_shell_quote(node.flarm_serial_path)} 2>/dev/null || true)\"\n"
        "printf 'primary_status_json<<EOF\\n'\n"
        f"cat {_shell_quote(_status_path_for_serial(node.primary_serial_path))} 2>/dev/null || true\n"
        "printf '\\nEOF\\n'\n"
        "printf 'flarm_status_json<<EOF\\n'\n"
        f"cat {_shell_quote(_status_path_for_serial(node.flarm_serial_path))} 2>/dev/null || true\n"
        "printf '\\nEOF\\n'\n"
        "printf 'processes<<EOF\\n'\n"
        "pgrep -fl 'kigo_xcvario_simulator.pty_bridge' || true\n"
        "printf 'EOF\\n'\n"
    )


def _stop_script(node: BridgeNode) -> str:
    serial_paths_json = json.dumps([node.primary_serial_path, node.flarm_serial_path])
    return (
        f"systemctl --user stop {PRIMARY_UNIT} 2>/dev/null || true\n"
        f"systemctl --user stop {FLARM_UNIT} 2>/dev/null || true\n"
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        "import os\n"
        "import signal\n"
        "\n"
        f"target_serial_paths = set(json.loads({_shell_quote(serial_paths_json)}))\n"
        "current_pid = os.getpid()\n"
        "for cmdline_path in Path('/proc').glob('[0-9]*/cmdline'):\n"
        "    try:\n"
        "        pid = int(cmdline_path.parent.name)\n"
        "        if pid == current_pid:\n"
        "            continue\n"
        "        parts = [part.decode('utf-8', 'ignore') for part in cmdline_path.read_bytes().split(b'\\0') if part]\n"
        "    except (OSError, ValueError):\n"
        "        continue\n"
        "    if not (len(parts) >= 3 and os.path.basename(parts[0]).startswith('python') and '-m' in parts and 'kigo_xcvario_simulator.pty_bridge' in parts):\n"
        "        continue\n"
        "    serial_path = ''\n"
        "    for index, part in enumerate(parts):\n"
        "        if part == '--serial-path' and index + 1 < len(parts):\n"
        "            serial_path = parts[index + 1]\n"
        "            break\n"
        "    if serial_path in target_serial_paths:\n"
        "        try:\n"
        "            os.kill(pid, signal.SIGTERM)\n"
        "        except ProcessLookupError:\n"
        "            pass\n"
        "PY\n"
    )


def _start_script(node: BridgeNode, primary_port: int, flarm_port: int) -> str:
    return (
        "set -eu\n"
        "command -v systemd-run >/dev/null\n"
        "mkdir -p /tmp/kigo-sim\n"
        f"{_stop_script(node)}"
        f"systemctl --user reset-failed {PRIMARY_UNIT} 2>/dev/null || true\n"
        f"systemctl --user reset-failed {FLARM_UNIT} 2>/dev/null || true\n"
        f"systemd-run --user --unit={PRIMARY_UNIT_NAME} "
        f"--working-directory={_shell_quote(node.workdir)} "
        "--property=Restart=always "
        "--property=RestartSec=1 "
        "--property=StartLimitIntervalSec=0 "
        f"--property=StandardOutput=append:{_shell_quote(node.workdir + '/pty-xcvario-to-mac.log')} "
        f"--property=StandardError=append:{_shell_quote(node.workdir + '/pty-xcvario-to-mac.log')} "
        "python3 -m kigo_xcvario_simulator.pty_bridge "
        f"--serial-path {_shell_quote(node.primary_serial_path)} "
        f"--tcp-host {_shell_quote(node.simulator_host)} "
        f"--tcp-port {int(primary_port)} "
        f"--status-path {_shell_quote(_status_path_for_serial(node.primary_serial_path))}\n"
        f"systemd-run --user --unit={FLARM_UNIT_NAME} "
        f"--working-directory={_shell_quote(node.workdir)} "
        "--property=Restart=always "
        "--property=RestartSec=1 "
        "--property=StartLimitIntervalSec=0 "
        f"--property=StandardOutput=append:{_shell_quote(node.workdir + '/pty-flarm-to-mac.log')} "
        f"--property=StandardError=append:{_shell_quote(node.workdir + '/pty-flarm-to-mac.log')} "
        "python3 -m kigo_xcvario_simulator.pty_bridge "
        f"--serial-path {_shell_quote(node.flarm_serial_path)} "
        f"--tcp-host {_shell_quote(node.simulator_host)} "
        f"--tcp-port {int(flarm_port)} "
        f"--status-path {_shell_quote(_status_path_for_serial(node.flarm_serial_path))}\n"
    )


def _parse_status(stdout: str) -> dict[str, str]:
    result: dict[str, str] = {}
    lines = stdout.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.endswith("<<EOF"):
            key = line.removesuffix("<<EOF")
            process_lines = []
            index += 1
            while index < len(lines) and lines[index] != "EOF":
                process_lines.append(lines[index])
                index += 1
            result[key] = "\n".join(process_lines).strip()
        elif "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
        index += 1
    return result


def _result_payload(action: str, nodes: list[dict[str, object]]) -> dict[str, object]:
    return {"action": action, "nodes": nodes}


def _required_text(value: Any, key_name: str) -> str:
    text = _text(value, default="")
    if not text:
        raise ValueError(f"{key_name} must be non-empty.")
    return text


def _text(value: Any, *, default: str) -> str:
    text = str(value if value is not None else default).strip()
    return text or default


def _port(value: Any, *, default: int) -> int:
    if value in (None, ""):
        return default
    port = int(value)
    if port <= 0 or port > 65535:
        raise ValueError("bridge port must be between 1 and 65535.")
    return port


def _positive_float(value: Any, *, default: float) -> float:
    if value in (None, ""):
        return float(default)
    number = float(value)
    if number <= 0.0:
        raise ValueError("bridge ready_timeout_s must be > 0.")
    return number


def _parse_status_json(raw: str) -> dict[str, object]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"parse_error": "invalid_json", "raw": text}
    return payload if isinstance(payload, dict) else {"parse_error": "not_object"}


def _status_path_for_serial(serial_path: str) -> str:
    return f"{serial_path}.status.json"


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
