# Simulator Panel

The panel is a lightweight local web UI for the operator on `Mac`.

## Start

```bash
python3 -m kigo_xcvario_simulator.panel.start_frontend --host 127.0.0.1 --port 8180
```

Then open [http://127.0.0.1:8180/](http://127.0.0.1:8180/).

## What The Panel Does

- stores the runtime URL in local browser storage,
- stores an optional start-airport ICAO code or free-text start-place query and sends it during `Connect`,
- sends the same start-airport/place field as the FLARM traffic anchor when `Apply Traffic` is pressed,
- loads the latest state from `GET /api/v1/simulation/state`,
- subscribes to `GET /api/v1/events`,
- sends operator commands for primary device selection, lifecycle, manual mode, wind, OAT and traffic,
- opens a snapshot chart for Raspberry Pi CPU temperature and CPU usage from `logs/CPU_temperature`,
- renders read-only ownship, traffic and health status,
- exposes traffic count, circling radius min/max, DDB-backed visible aircraft IDs, a straight/orbit
  traffic-motion toggle, and an optional collision-course mode for contact `1`.

For manual `straight`, `Climb Min/Max` set the vario sinusoid bounds, such as
`-2 m/s` and `+4 m/s`, with small seeded jitter. Blank fields or both fields set
to `0` keep level flight.

When the start-airport field is filled, the runtime accepts either a
four-character ICAO code or a free-text place/country query such as
`Minden Tahoe USA`. ICAO values search local OpenAIP `*_apt.json` files.
Non-ICAO values use the configured online geocoder to resolve latitude/longitude.
Resolved coordinates are cached in `.cache/airport_icao_cache.json`, and the
ownship is reset there on the ground. Online geocoder results do not include
terrain elevation, so they start at `0 m` GPS altitude. The default geocoder URL
can be changed with `KIGO_GEOCODER_SEARCH_URL`, and its User-Agent with
`KIGO_GEOCODER_USER_AGENT`.

`Apply Traffic` restarts generated FLARM contacts from scratch. When
`Start airport or place` is filled, that point becomes the traffic placement
anchor without moving the current ownship; blanking the field falls back to the
current ownship position for the new traffic start.

## Expected Runtime Config

The default panel port is `8180`, which matches the default `cors_allowed_origins` in
[runtime.example.json](../examples/runtime.example.json).
