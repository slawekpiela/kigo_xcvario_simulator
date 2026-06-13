# Simulator Panel

The panel is a lightweight local web UI for the operator on `Mac`.

## Start

```bash
python3 -m kigo_xcvario_simulator.panel.start_frontend --host 127.0.0.1 --port 8180
```

Then open [http://127.0.0.1:8180/](http://127.0.0.1:8180/).

## What The Panel Does

- stores the runtime URL in local browser storage,
- stores an optional start-airport ICAO code and sends it during `Connect`,
- loads the latest state from `GET /api/v1/simulation/state`,
- subscribes to `GET /api/v1/events`,
- sends operator commands for primary device selection, lifecycle, manual mode, wind, OAT and traffic,
- opens a snapshot chart for Raspberry Pi CPU temperature and CPU usage from `logs/CPU_temperature`,
- renders read-only ownship, traffic and health status,
- exposes traffic count, visible aircraft IDs and an optional collision-course mode for contact `1`.

When the start-airport ICAO field is filled, the runtime searches local OpenAIP
`*_apt.json` files, writes the resolved coordinate to `.cache/airport_icao_cache.json`,
and resets the ownship to that airport on the ground. The built-in known
positions include `FWCT` for Worcester, South Africa.

## Expected Runtime Config

The default panel port is `8180`, which matches the default `cors_allowed_origins` in
[runtime.example.json](../examples/runtime.example.json).
