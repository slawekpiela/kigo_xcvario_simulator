"""SSH-backed control for simulator TCP-to-PTY bridges on remote hosts."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Any


PRIMARY_UNIT = "kigo-xcvario-pty-xcvario.service"
FLARM_UNIT = "kigo-xcvario-pty-flarm.service"
PRIMARY_UNIT_NAME = PRIMARY_UNIT.removesuffix(".service")
FLARM_UNIT_NAME = FLARM_UNIT.removesuffix(".service")
DEFAULT_PRIMARY_SERIAL_PATH = "/tmp/kigo-sim/xcvario"
DEFAULT_FLARM_SERIAL_PATH = "/tmp/kigo-sim/flarm"


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
            status = _node_status(node)
            status["action_returncode"] = run.returncode
            status["action_stdout"] = run.stdout.strip()
            status["action_stderr"] = run.stderr.strip()
            results.append(status)
        return _result_payload("start", results)

    def stop(self, payload: dict[str, object]) -> dict[str, object]:
        config = _parse_payload(payload)
        results = []
        for node in config.nodes:
            run = _run_remote(node, _stop_script())
            status = _node_status(node)
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
    run = _run_remote(node, _status_script())
    parsed = _parse_status(run.stdout)
    return {
        "id": node.node_id,
        "ssh_target": node.ssh_target,
        "simulator_host": node.simulator_host,
        "workdir": node.workdir,
        "primary_active": parsed.get("primary") == "active",
        "flarm_active": parsed.get("flarm") == "active",
        "primary_status": parsed.get("primary", "unknown"),
        "flarm_status": parsed.get("flarm", "unknown"),
        "processes": parsed.get("processes", ""),
        "returncode": run.returncode,
        "stdout": run.stdout.strip(),
        "stderr": run.stderr.strip(),
    }


def _run_remote(node: BridgeNode, script: str) -> subprocess.CompletedProcess[str]:
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


def _status_script() -> str:
    return (
        f"printf 'primary=%s\\n' \"$(systemctl --user is-active {PRIMARY_UNIT} 2>/dev/null || true)\"\n"
        f"printf 'flarm=%s\\n' \"$(systemctl --user is-active {FLARM_UNIT} 2>/dev/null || true)\"\n"
        "printf 'processes<<EOF\\n'\n"
        "pgrep -fl 'kigo_xcvario_simulator.pty_bridge' || true\n"
        "printf 'EOF\\n'\n"
    )


def _stop_script() -> str:
    return (
        f"systemctl --user stop {PRIMARY_UNIT} 2>/dev/null || true\n"
        f"systemctl --user stop {FLARM_UNIT} 2>/dev/null || true\n"
    )


def _start_script(node: BridgeNode, primary_port: int, flarm_port: int) -> str:
    return (
        "set -eu\n"
        "mkdir -p /tmp/kigo-sim\n"
        f"{_stop_script()}"
        f"systemd-run --user --unit={PRIMARY_UNIT_NAME} "
        f"--working-directory={_shell_quote(node.workdir)} "
        f"--property=StandardOutput=append:{_shell_quote(node.workdir + '/pty-xcvario-to-mac.log')} "
        f"--property=StandardError=append:{_shell_quote(node.workdir + '/pty-xcvario-to-mac.log')} "
        "python3 -m kigo_xcvario_simulator.pty_bridge "
        f"--serial-path {_shell_quote(node.primary_serial_path)} "
        f"--tcp-host {_shell_quote(node.simulator_host)} "
        f"--tcp-port {int(primary_port)}\n"
        f"systemd-run --user --unit={FLARM_UNIT_NAME} "
        f"--working-directory={_shell_quote(node.workdir)} "
        f"--property=StandardOutput=append:{_shell_quote(node.workdir + '/pty-flarm-to-mac.log')} "
        f"--property=StandardError=append:{_shell_quote(node.workdir + '/pty-flarm-to-mac.log')} "
        "python3 -m kigo_xcvario_simulator.pty_bridge "
        f"--serial-path {_shell_quote(node.flarm_serial_path)} "
        f"--tcp-host {_shell_quote(node.simulator_host)} "
        f"--tcp-port {int(flarm_port)}\n"
    )


def _parse_status(stdout: str) -> dict[str, str]:
    result: dict[str, str] = {}
    lines = stdout.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line == "processes<<EOF":
            process_lines = []
            index += 1
            while index < len(lines) and lines[index] != "EOF":
                process_lines.append(lines[index])
                index += 1
            result["processes"] = "\n".join(process_lines)
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


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
