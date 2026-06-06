# KIGO Vario Simulator

This directory contains the complete test simulator for KIGO:

- remote runtime for `Pi` or `VM`,
- selectable `XCvario` / `SxHAWK` primary TCP adapter and `FLARM` TCP adapter,
- control API with JSON and SSE,
- local panel for `Mac`,
- examples, smoke tests and runbook material.

## Layout

- `config.py`, `contracts.py`, `state.py`: shared runtime contracts
- `flight_model.py`, `traffic_model.py`, `presets.py`, `variation.py`: simulation core
- `nmea.py`, `xcvario_adapter.py`, `sxhawk_adapter.py`, `flarm_adapter.py`: wire-format and TCP adapters
- `scheduler.py`, `session.py`, `control_api.py`: runtime loop and control plane
- `start_remote_runtime.py`: CLI entrypoint for the remote runtime
- `panel/`: static operator UI served locally on `Mac`
- `examples/runtime.example.json`: baseline runtime config
- `examples/xcsoar_profile_snippet.txt`: sample `XCSoar/KIGO` profile snippet
- `examples/igc_logs/`: sample IGC logs exposed by the simulated FLARM logger when `../kigo_nav/logs` is empty

## Quick Start

### 1. Prepare Runtime Config On Pi Or VM

Copy and adjust the example:

```bash
cp kigo_xcvario_simulator/examples/runtime.example.json /tmp/runtime.local.json
```

Recommended edits:

- set `primary_device` to `xcvario` or `sxhawk`,
- keep `xcvario.port=4353` and `flarm.port=4354`; the `xcvario` block is the primary device endpoint for both protocols,
- set `cors_allowed_origins` to the panel URL you will use on the `Mac`,
- verify `home_position`.

### 2. Start The Remote Runtime

```bash
python3 -m kigo_xcvario_simulator.start_remote_runtime --config /tmp/runtime.local.json
```

This starts:

- active primary-device TCP listener: `XCvario` or `SxHAWK`,
- `FLARM` TCP listener,
- control API,
- telemetry scheduler.

The default `XCvario` telemetry cadence mirrors the real device firmware:
baro/vario sentences are emitted at `2 Hz`, while simulator GPS sentences are
kept at `1 Hz`.
Wind is emitted on the same `XCvario` stream as `$WIMWV,<direction>,T,<speed>,K,A`,
matching the real device output for true wind in `km/h`.
OAT defaults to `18.0 deg C` and is emitted in the `PXCV` and `POV` pressure
sentences used by `kigo_nav`.
The `XCvario` stream also emits `LXWP0` with the current vario value as a
compatibility fallback for `kigo_nav` profiles that accidentally keep the `LX`
driver on the primary port.
Device QNH and device barometric altitude can be adjusted from the panel.  A
QNH change is emitted in the primary-device protocol, while an altitude change
is converted to the matching QNH for the current static pressure and then
emitted the same way.
Both the `XCvario` primary endpoint and the separate `FLARM` endpoint emulate
the IGC FLARM declaration/logger protocol used by XCSoar: `PFLAC`
declaration/config commands are acknowledged and stored, while `$PFLAX` switches
that connection to the FLARM binary logger protocol. Logger records are loaded
from sibling `../kigo_nav/logs/*.igc` files when present; otherwise the
simulator falls back to packaged sample flights in
`kigo_xcvario_simulator/examples/igc_logs`.
During `circling_left`/`circling_right`, `$PXCV` also includes synthetic AHRS
roll angle in the XCVario roll field. The bank magnitude varies smoothly between
`35` and `50` degrees; left turns are emitted as negative roll and right turns
as positive roll.
FLARM traffic contacts use a curated FLARMnet DDB sample downloaded on
2026-06-06 from `https://www.flarmnet.org/files/ddb.json`; records are filtered
to identified/tracked FLARM devices with Polish registrations and non-empty
competition IDs. `$PFLAA`/`$PFLAU` emit the real six-hex-digit device ID, while
the control API and panel also expose competition ID, registration and model.

The `SxHAWK` telemetry stream follows the LXNAV/LX protocol parsed by the
`LX`/LXNAV driver in `kigo_nav`: `GPRMC`, `GPGGA`, `LXWP0`, `LXWP1`, `LXWP2`
and `LXWP3`. It accepts `PFLX2`/`PFLX3` and `PLXV0` write-side settings for
MC, ballast, bugs, QNH and device altitude.

When `kigo_nav` or another primary-device client connects, the runtime
automatically activates manual `on_ground` at the configured home position:
speed `0 km/h`, vertical speed `0 m/s`, glider on the runway. Reconnects do
not overwrite an active manual-mode command, so an operator-set speed or
altitude keeps flowing after `Apply Manual Mode`.

### 3. Start The Panel On Mac

```bash
python3 -m kigo_xcvario_simulator.panel.start_frontend --host 127.0.0.1 --port 8180
```

Open [http://127.0.0.1:8180/](http://127.0.0.1:8180/), enter:

- runtime URL, for example `http://192.168.0.50:8181`,
- choose `XCvario` or `SxHAWK` as the active primary device when needed.

### 4. Configure XCSoar/KIGO Test Profile

Use the snippet from [examples/xcsoar_profile_snippet.txt](kigo_xcvario_simulator/examples/xcsoar_profile_snippet.txt):

```text
DeviceA="XCVario"
PortType="tcp_client"
PortIPAddress="<runtime-host>"
PortTCPPort="4353"

DeviceB="FLARM"
Port2Type="tcp_client"
Port2IPAddress="<runtime-host>"
Port2TCPPort="4354"
```

Replace `<runtime-host>` with the `Pi` or `VM` host that runs the simulator.
For SxHAWK, set `primary_device="sxhawk"` in the runtime config or panel and
use [examples/sxhawk_profile_snippet.txt](kigo_xcvario_simulator/examples/sxhawk_profile_snippet.txt).
Kigo/Nav stores the LXNAV/SxHAWK protocol driver under the internal name `LX`:

```text
DeviceA="LX"
PortType="tcp_client"
PortIPAddress="<runtime-host>"
PortTCPPort="4353"
```

### 4a. Run Pi And VM In Parallel

The runtime accepts multiple TCP clients on each simulator endpoint. Point both
the `Pi` and `VM` navigation profiles at the same runtime host:

- primary device stream: `<runtime-host>:4353`,
- FLARM stream: `<runtime-host>:4354`.

Every connected client receives the same telemetry frames. Write-side device
settings such as QNH, altitude, MacCready, ballast and bugs are accepted from
any connected primary-device client; if both clients send settings, the latest
valid command wins.

### 5. Reuse An Existing Serial Profile Such As `SLAWEK2`

If the navigation profile already expects serial devices instead of `tcp_client`,
keep the profile in serial mode and expose the simulator ports through stable PTY
paths.

Start one bridge per device on the `Pi` or `VM` that runs the simulator:

```bash
python3 -m kigo_xcvario_simulator.pty_bridge \
  --serial-path /tmp/kigo-sim/xcvario \
  --tcp-host 127.0.0.1 \
  --tcp-port 4353

python3 -m kigo_xcvario_simulator.pty_bridge \
  --serial-path /tmp/kigo-sim/flarm \
  --tcp-host 127.0.0.1 \
  --tcp-port 4354
```

Then point the existing profile at those serial paths. For a profile shaped like
`SLAWEK2.top`, the relevant entries look like:

```text
DeviceA="XCVario"
PortType="serial"
PortPath="/tmp/kigo-sim/xcvario"
PortEnabled="1"

DeviceB=""
Port2Type="disabled"
Port2Enabled="0"

DeviceC="FLARM"
Port3Type="serial"
Port3Path="/tmp/kigo-sim/flarm"
Port3Enabled="1"
```

This lets `kigo_nav` keep using the existing serial-profile layout while the
simulator still runs over TCP underneath.
For SxHAWK, switch the runtime to `primary_device="sxhawk"`, expose a matching
PTY such as `/tmp/kigo-sim/sxhawk`, and set `DeviceA="LX"` with
`PortPath="/tmp/kigo-sim/sxhawk"`.

## Manual Flow

1. Connect the panel.
2. Choose a `Manual Mode` phase; `on_ground` is the default after an `XCvario` client connect/reconnect.
3. Set `Flight Altitude [m]` when using `straight`; the model ramps smoothly from the current altitude to that target at `0.1 m/s` instead of jumping.
4. Set `Climb Min/Max [m/s]` for `straight` when you want the post-ramp vario, and therefore trail colour, to follow a sinusoid between those values over a `60 s` cycle.
5. Set circling speed min/max in `Manual Mode` when using `circling_left` or `circling_right`.
6. Set wind direction and speed; the runtime sends them to `kigo_nav` as `WIMWV`.
7. Set OAT when you need a non-default outside air temperature in the `PXCV`/`POV` stream.
8. Set `QNH [hPa]` or `Wysokosc [m]` in `Atmosphere` to adjust the simulated device altimeter; changing one recalculates the other from the current static pressure.
9. Adjust traffic count if needed, and enable `collision course` when you want the first traffic contact to converge on the ownship.
10. Use `Start / Resume`, `Pause`, `Reset` or `Apply Manual Mode`.
11. Watch `Ownship`, `Traffic` and `Health` update from `GET /state` and `SSE`, including each emitted FLARM ID and competition ID.

## Test Commands

```bash
python3 -m unittest discover -s tests -p 'test_xcvario_sim_*.py'
```
