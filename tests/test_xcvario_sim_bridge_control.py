import unittest

from kigo_xcvario_simulator.bridge_control import _parse_payload


class BridgeControlPayloadTests(unittest.TestCase):
    def test_remote_pi_or_vm_reject_loopback_simulator_host(self):
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

        with self.assertRaisesRegex(ValueError, "Mac runtime"):
            _parse_payload(payload)

    def test_remote_pi_accepts_mac_lan_simulator_host(self):
        config = _parse_payload(
            {
                "nodes": [
                    {
                        "id": "pi",
                        "ssh_target": "admin@192.168.0.114",
                        "simulator_host": "192.168.0.106",
                        "workdir": "/home/admin/kigo_xcvario_simulator",
                    }
                ],
            }
        )

        self.assertEqual(config.nodes[0].simulator_host, "192.168.0.106")


if __name__ == "__main__":
    unittest.main()
