import json
import subprocess
import unittest
from unittest.mock import patch

from kigo_xcvario_simulator.bridge_control import (
    BridgeNode,
    _node_status,
    _parse_payload,
    _run_remote,
    _start_reverse_tunnel_script,
    _start_script,
)


class BridgeControlPayloadTests(unittest.TestCase):
    def test_remote_pi_or_vm_accept_loopback_simulator_host(self):
        payload = {
            "nodes": [
                {
                    "id": "vm",
                    "ssh_target": "slawek@172.16.119.135",
                    "simulator_host": "127.0.0.1",
                    "workdir": "/home/slawek/kigo_xcvario_simulator",
                }
            ],
        }

        config = _parse_payload(payload)

        self.assertEqual(config.nodes[0].simulator_host, "127.0.0.1")

    def test_remote_pi_accepts_lan_simulator_host(self):
        config = _parse_payload(
            {
                "nodes": [
                    {
                        "id": "pi",
                        "ssh_target": "admin@192.168.0.114",
                        "simulator_host": "127.0.0.1",
                        "workdir": "/home/admin/kigo_xcvario_simulator",
                        "reverse_tunnel": True,
                    }
                ],
            }
        )

        self.assertEqual(config.nodes[0].simulator_host, "127.0.0.1")
        self.assertTrue(config.nodes[0].reverse_tunnel)

    def test_local_ssh_target_runs_without_ssh(self):
        run = _run_remote(
            BridgeNode(
                node_id="vm",
                ssh_target="localhost",
                simulator_host="127.0.0.1",
                workdir="/tmp",
            ),
            "printf local-bridge",
        )

        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout, "local-bridge")

    def test_remote_ssh_skips_missing_identity_and_accepts_known_host(self):
        node = BridgeNode(
            node_id="pi",
            ssh_target="admin@192.168.0.114",
            simulator_host="172.16.119.135",
            workdir="/home/admin/kigo_xcvario_simulator",
            identity_file="/missing/kigo_pi",
        )

        with (
            patch("kigo_xcvario_simulator.bridge_control._is_local_target", return_value=False),
            patch(
                "kigo_xcvario_simulator.bridge_control.subprocess.run",
                return_value=subprocess.CompletedProcess(["ssh"], 0, "ok", ""),
            ) as run_mock,
        ):
            run = _run_remote(node, "printf ok")

        command = run_mock.call_args.args[0]
        self.assertEqual(run.returncode, 0)
        self.assertIn("StrictHostKeyChecking=accept-new", command)
        self.assertNotIn("-i", command)

    def test_node_status_requires_units_pty_and_tcp_connection(self):
        node = BridgeNode(
            node_id="pi",
            ssh_target="admin@192.168.0.114",
            simulator_host="127.0.0.1",
            workdir="/home/admin/kigo_xcvario_simulator",
        )
        stdout = "\n".join(
            [
                "primary=active",
                "flarm=active",
                "primary_pty_exists=true",
                "flarm_pty_exists=true",
                "primary_pty_target=/dev/pts/11",
                "flarm_pty_target=/dev/pts/12",
                "primary_status_json<<EOF",
                json.dumps({"tcp_connected": True, "bytes_tcp_to_pty": 120, "bytes_pty_to_tcp": 7}),
                "EOF",
                "flarm_status_json<<EOF",
                json.dumps({"tcp_connected": True, "bytes_tcp_to_pty": 80, "bytes_pty_to_tcp": 0}),
                "EOF",
                "processes<<EOF",
                "123 python3 -m kigo_xcvario_simulator.pty_bridge --serial-path /tmp/kigo-sim/xcvario",
                "EOF",
            ]
        )

        with patch(
            "kigo_xcvario_simulator.bridge_control._run_remote",
            return_value=subprocess.CompletedProcess(["ssh"], 0, stdout, ""),
        ):
            status = _node_status(node)

        self.assertTrue(status["ready"])
        self.assertTrue(status["primary_ready"])
        self.assertTrue(status["flarm_ready"])
        self.assertEqual(status["primary_pty_target"], "/dev/pts/11")
        self.assertEqual(status["primary_bytes_tcp_to_pty"], 120)

    def test_start_script_runs_bridges_with_restart_policy_and_status_files(self):
        node = BridgeNode(
            node_id="pi",
            ssh_target="admin@192.168.0.114",
            simulator_host="127.0.0.1",
            workdir="/home/admin/kigo_xcvario_simulator",
        )

        script = _start_script(node, 4353, 4354)

        self.assertIn("--property=Restart=always", script)
        self.assertIn("--property=RestartSec=1", script)
        self.assertIn("--status-path '/tmp/kigo-sim/xcvario.status.json'", script)
        self.assertIn("--status-path '/tmp/kigo-sim/flarm.status.json'", script)

    def test_reverse_tunnel_script_opens_remote_forwards_to_controller_runtime(self):
        node = BridgeNode(
            node_id="pi",
            ssh_target="admin@192.168.0.114",
            simulator_host="127.0.0.1",
            workdir="/home/admin/kigo_xcvario_simulator",
            identity_file="/missing/kigo_pi",
            reverse_tunnel=True,
        )

        script = _start_reverse_tunnel_script(node, 4353, 4354)

        self.assertIn("--unit=kigo-xcvario-tunnel-pi", script)
        self.assertIn("-o ExitOnForwardFailure=yes", script)
        self.assertIn("-R 127.0.0.1:4353:127.0.0.1:4353", script)
        self.assertIn("-R 127.0.0.1:4354:127.0.0.1:4354", script)


if __name__ == "__main__":
    unittest.main()
