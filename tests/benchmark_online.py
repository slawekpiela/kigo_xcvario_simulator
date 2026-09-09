"""Bounded load check of the real HTTP facade and Vario/FLARM sockets."""
import argparse
import concurrent.futures
import http.client
import json
from pathlib import Path
import resource
import threading
import time
from kigo_xcvario_simulator.config import load_runtime_config
from kigo_xcvario_simulator.contracts import ManualModeInput
from kigo_xcvario_simulator.online import OnlineServer, SessionRegistry
from kigo_xcvario_simulator.state import FlightPhase


def run(count, seconds):
    registry = SessionRegistry(load_runtime_config(Path(__file__).resolve().parents[1] /
                               "kigo_xcvario_simulator/examples/runtime.example.json"), count)
    server = OnlineServer(("127.0.0.1", 0), registry)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        for n in range(count):
            session = registry.get(f"load-{n}", create=True, peer=str(n))
            session.runtime.set_manual_mode(ManualModeInput(phase=FlightPhase.STRAIGHT, speed_kmh=110,
                                                            baro_altitude_m=1500 + n * 10))
            session.runtime.set_traffic_config(True, 29, False)
            session.runtime.start_simulation()
        barrier = threading.Barrier(count * 2)

        def client(args):
            n, channel = args
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            body = {"application_id": f"load-{n}", "channel": channel, "client": f"{n:032x}", "data": ""}
            barrier.wait()
            end, sequence, latencies, total_bytes = time.monotonic() + seconds, 1, [], 0
            try:
                while time.monotonic() < end:
                    body["sequence"] = sequence
                    start = time.monotonic()
                    connection.request("POST", "/simulator/api/exchange", json.dumps(body), {"Content-Type": "application/json"})
                    response = connection.getresponse()
                    data = response.read()
                    if response.status != 200 or not data.startswith(b"OK\n"):
                        raise RuntimeError((response.status, data[:100]))
                    total_bytes += len(bytes.fromhex(data[3:].decode()))
                    latencies.append(time.monotonic() - start)
                    sequence += 1
                if not total_bytes:
                    raise RuntimeError("No telemetry received")
                return latencies, total_bytes
            finally:
                connection.close()

        before = resource.getrusage(resource.RUSAGE_SELF)
        with concurrent.futures.ThreadPoolExecutor(max_workers=count * 2) as pool:
            results = list(pool.map(client, [(n, channel) for n in range(count) for channel in ("vario", "flarm")]))
        after = resource.getrusage(resource.RUSAGE_SELF)
        samples = sorted(value for values, _ in results for value in values)
        print(json.dumps({"sessions": count, "channels": count*2, "seconds": seconds,
                          "exchanges": len(samples), "bytes": sum(size for _, size in results),
                          "p95_ms": round(samples[int(len(samples)*0.95)]*1000, 1),
                          "cpu_seconds": round(after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime, 2),
                          "peak_rss_kib": after.ru_maxrss}))
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
        registry.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=10)
    args = parser.parse_args()
    run(args.sessions, args.seconds)
