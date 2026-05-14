# Simulator Panel

The panel is a lightweight local web UI for the operator on `Mac`.

## Start

```bash
python3 -m kigo_xcvario_simulator.panel.start_frontend --host 127.0.0.1 --port 8180
```

Then open [http://127.0.0.1:8180/](http://127.0.0.1:8180/).

## What The Panel Does

- stores the runtime URL and simulator token in local browser storage,
- loads the latest state from `GET /api/v1/simulation/state`,
- subscribes to `GET /api/v1/events` with the same token,
- sends operator commands for primary device selection, lifecycle, manual mode, wind, OAT and traffic,
- renders read-only ownship, traffic and health status,
- exposes traffic count, visible aircraft IDs and an optional collision-course mode for contact `1`.

## Expected Runtime Config

The default panel port is `8180`, which matches the default `cors_allowed_origins` in
[runtime.example.json](../examples/runtime.example.json).
