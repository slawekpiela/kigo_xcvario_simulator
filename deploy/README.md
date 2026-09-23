# Online simulator on Anton

The service listens only on `127.0.0.1:8010`. Public URL:
`https://api.koioslabs.pl/simulator/`.

Install source (including package data) into `/home/slawek/kigo-simulator-online`.
No additional Python dependencies are required. Install the supplied user unit
as `~/.config/systemd/user/kigo-simulator-online.service`, reload the user manager
and enable/start the unit. Do not publish the legacy runtime API or TCP sockets.

The `api.koioslabs.pl` gateway forwards the public `/simulator/` panel and its
bounded API routes to this loopback service. Gateway and Cloudflare routing are
owned by `kigo_services`; deploying this package does not require changing them.
Do not restore the retired public Hermes5 simulator route.

Verify the local service, public panel, two independent Application IDs, a
duplicate-ID rejection from another panel client, and both device channels.
Keep test IDs disposable. Sessions
close immediately when their browser page or `kigoconcept.pl` popup closes and
expire after 15 minutes without panel/device activity; idle device connections
are closed after 30 seconds. A service restart loses active sessions; explicitly
open/start a session again in the panel. Existing active sessions aren't reset
by opening the panel or reconnecting either device channel.

Status: `systemctl --user status kigo-simulator-online.service`.
Stop: `systemctl --user stop kigo-simulator-online.service`.
Rollback: restore the previous simulator source from the deployment backup and
restart this user service. This deployment does not stop the old lab runtime.

The public API implements a simulator key, not pilot account login. One browser
panel owns an active Application ID; another panel client receives HTTP 409 and
must use a different ID. The owning panel sends a random 32-hex token on session,
control and close requests. Device exchange continues to use the Application ID
and its separate device client token. No mail/account permissions are granted.
No IDs or protocol bytes are written to access logs.
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
