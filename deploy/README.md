# Online simulator on Anton

The service listens only on `127.0.0.1:8010`. Public URL:
`https://hermes5.koioslabs.pl/simulator/`.

Install source (including package data) into `/home/slawek/kigo-simulator-online`.
No additional Python dependencies are required. Install the supplied user unit
as `~/.config/systemd/user/kigo-simulator-online.service`, reload the user manager
and enable/start the unit. Do not publish the legacy runtime API or TCP sockets.

Hermes5 already has a public Cloudflare route to the private proxy on port 8005.
Install the narrow route using:

```sh
python3 deploy/add_hermes5_route.py /home/slawek/kigo-hermes5-rag-proxy.py
docker compose -p kigo-security-proxies \
  -f /home/slawek/kigo-security-stage1/hermes-proxies-compose.yaml restart hermes5
```

The installer preserves the proxy's existing authentication and routes and
creates `kigo-hermes5-rag-proxy.py.before-task482`. The restart briefly interrupts
Hermes5 requests. Verify `/stats/` still returns 401 and `/rag/index` 404 without
credentials. Keep Compose and its existing env_file; never replace the container
with the historical bare docker-run recipe. `hermes.koioslabs.pl` is protected
by Cloudflare Access and cannot serve the automatic device client; do not remove
that protection. The system cloudflared config needs no simulator rule.

Verify the local and public `/simulator/health`, the panel, two independent
Application IDs, and both device channels. Keep test IDs disposable. Sessions
expire after 15 minutes without panel/device activity; idle device connections
are closed after 30 seconds. A service restart loses active sessions; explicitly
open/start a session again in the panel. Existing active sessions aren't reset
by opening the panel or reconnecting either device channel.

Status: `systemctl --user status kigo-simulator-online.service`.
Stop: `systemctl --user stop kigo-simulator-online.service`.
Rollback: stop the new service, remove only the added simulator route from the
Hermes5 proxy (or restore the backup if no later edits exist) and restart that
Compose service. This deployment does not stop the old lab runtime.

The public API implements a shared-key simulator, not pilot account login:
anyone given an Application ID can operate that simulation. No mail/account
permissions are granted. No IDs or protocol bytes are written to access logs.
Keep bridge administration private. Limits: 50 sessions, eight byte connections
per session, 16 KiB per exchange, 256 concurrent HTTP connections, one new
session per second per direct peer. Behind the local Cloudflare tunnel the
creation limit is shared by that peer; existing sessions remain accessible.

The device protocol POSTs JSON to `/simulator/api/exchange` containing
`application_id`, `channel` (`vario`/`flarm`), a random 32-hex `client`, an integer
`sequence` starting at 1, and hex `data`. Response is `OK\n` followed by hex bytes.
An empty exchange waits at most 200 ms. Repeating the previous sequence with
identical bytes returns its cached response without repeating device commands.
409/410 requires a fresh client ID and sequence; never replay old pending
commands into a new connection. 404 means waiting for a panel-created session.

Bounded load check: `PYTHONPATH=. python3 tests/benchmark_online.py --sessions 50 --seconds 10`.
