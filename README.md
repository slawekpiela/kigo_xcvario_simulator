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
FLARM traffic contacts start with six decoded FLARMNet IDs: `DDA857`,
`DDA85A`, `DDA85C`, `DDA86A`, `DDA88F` and `DDA896`, followed by 23
authentic FLARMnet-backed devices with competition signs. The runtime and panel
default to publishing all 29 contacts. Default contacts stay between 5 km and
30 km from the selected `Start airport or place` when one is configured, falling
back to the ownship at traffic start; after that only `$PFLAA` reporting is
relative to the current ownship position. Default contacts use deterministic
per-contact speeds between `100` and `200 km/h` (`27.8` to `55.6 m/s`), for both
`orbit` and `straight` motion. In each orbit cycle they climb by `300` to
`1000 m`, then fly straight for `2 min` with zero climb before starting the next
orbit. Orbit climb rate is positive between `0.51` and `4.0 m/s`.
The panel Traffic section can set circling radius min/max; every orbiting contact
gets a deterministic random maximum ellipse radius from that range. It can also
toggle default contacts between `orbit` and `straight` motion. `Apply Traffic`
restarts generated traffic and uses the current `Start airport or place` field
as the placement anchor when it is filled. The optional `collision course` mode
still makes the first contact converge on the ownship.
`$PFLAA`/`$PFLAU` emit the six-hex-digit device ID, while the control API and
panel also expose competition ID, registration, model labels and speed.

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
- optional `Start airport or place`; the field accepts either a four-character ICAO code or a
  free-text place/country query such as `Minden Tahoe USA`. ICAO values use local OpenAIP airport
  data; non-ICAO values use the configured online geocoder to resolve latitude/longitude, cache the
  result under `.cache/airport_icao_cache.json`, and place the glider there on the ground. Online
  geocoder results do not include terrain elevation, so they start at `0 m` GPS altitude.
  The default geocoder URL can be changed with `KIGO_GEOCODER_SEARCH_URL`, and its User-Agent with
  `KIGO_GEOCODER_USER_AGENT`.
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

Current lab setup for identical VM/Pi display keeps the runtime only on the VM.
The Pi local `kigo-xcvario-runtime.service` stays disabled, and the Pi serial
bridges connect through the VM `kigo-xcvario-tunnel-pi.service` reverse tunnel
to VM ports `4353` and `4354`.

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

When the Pi is outside the LAN but reachable through Tailscale, keep the
runtime on the VM and use the VM SSH alias `kigo-pi-tail` as the `PI Bridge
Target`. The VM alias reaches the Tailscale host `kigo-pi` and the bridge API
starts the reverse tunnel so the Pi PTYs still connect to the runtime's local
`127.0.0.1:4353` and `127.0.0.1:4354`.

## Manual Flow

1. Connect the panel.
2. Choose a `Manual Mode` phase; `on_ground` is the default after an `XCvario` client connect/reconnect.
3. Set `Flight Altitude [m]` when using `straight`; the model applies that GPS/baro altitude immediately so the change is visible right after `Apply Manual Mode`.
4. In `straight`, fill `Climb Min/Max [m/s]` to set the sinusoid bounds for vario, for example `-2` and `4`; blank fields or both set to `0` keep level flight.
5. Set circling speed min/max in `Manual Mode` when using `circling_left` or `circling_right`.
6. Set wind direction and speed; the runtime sends them to `kigo_nav` as `WIMWV`.
7. Set OAT when you need a non-default outside air temperature in the `PXCV`/`POV` stream.
8. Set `QNH [hPa]` or `Wysokosc [m]` in `Atmosphere` to adjust the simulated device altimeter; changing one recalculates the other from the current static pressure.
9. Keep the default 29 traffic contacts for the full FLARM set, lower the count if needed, and press `Apply Traffic` to restart generated traffic around the current `Start airport or place` field. Enable `collision course` when you want the first traffic contact to converge on the ownship.
10. Use `Start / Resume`, `Pause`, `Reset` or `Apply Manual Mode`.
11. Watch `Ownship`, `Traffic` and `Health` update from `GET /state` and `SSE`, including each emitted FLARM ID and competition ID.

If Kigo's `Devices` screen shows `XCVario ... No data` while the bridge is
connected, check the panel `Health` scheduler fields or `GET /state`. A stale
timestamp with a scheduler `last_error` means the runtime needs restart; current
builds keep the scheduler alive after tick errors and cap impossible barometric
altitudes before they can stop the telemetry thread.

## Test Commands

```bash
python3 -m unittest discover -s tests -p 'test_xcvario_sim_*.py'
```

## Android Phone USB Bridge APK

For a phone connected to the Mac over USB debugging, this repository includes a
separate helper APK under [android_bridge](android_bridge). The APK listens on
the phone at `127.0.0.1:4353` and `127.0.0.1:4354`, then connects upstream to
`127.0.0.1:44353` and `127.0.0.1:44354`; `adb reverse` maps those upstream
ports back to the simulator TCP ports on the Mac.

The local panel's `Bridge Control` section shows Android phone bridge status
from the Mac-side `/api/v1/android-bridge/status` endpoint. `Connected` requires
ADB device state, installed/running bridge APK, `adb reverse` for both streams
and open Mac ports; `Transmitting` also requires established phone sockets.

Build and install:

```bash
./android_bridge/install_bridge.sh
```

Configure Kigo/Nav on the phone as TCP clients:

```text
DeviceA="XCVario"
PortType="tcp_client"
PortIPAddress="127.0.0.1"
PortTCPPort="4353"

DeviceB="FLARM"
Port2Type="tcp_client"
Port2IPAddress="127.0.0.1"
Port2TCPPort="4354"
```

This bridge is TCP-only. A normal Android APK cannot expose a virtual serial
device to another APK without additional app support or root access.
