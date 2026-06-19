# Project Technical Documentation

This file is the durable technical memory for this project. Keep it concise, practical, and useful for future code work.

## How To Maintain This File

- Add information discovered during code analysis when it can shorten future investigation.
- Update this file before committing when code changes affect behavior, architecture, configuration, workflows, or project assumptions.
- Prefer concrete facts, file paths, commands, data flows, constraints, and decisions over broad summaries.
- If a commit does not require a documentation update, record that decision in the commit message with `Docs-Impact: none - <reason>`.

## Project Overview

_To be filled as durable knowledge is discovered._

## Architecture And Data Flow

- Wind handling for ownship is split by vector type. `ScenarioOrchestrator.tick()` passes the current
  `WindState` into `FlightModel.step()`, and the flight model advances latitude/longitude with the
  wind-adjusted ground vector while keeping `OwnshipState.speed_kmh` and `track_deg` as the air
  vector/heading used by vario/heading sentences.
- XCVario/SxHAWK GPS output then derives `$GPRMC` speed/course over ground by applying the same
  true-wind vector to the ownship air vector, while `$GPGGA` carries the already wind-drifted
  position and `$HCHDM`/`$LXWP0` keep the air heading/airspeed-style values.
- The XCVario adapter exposes airspeed to `kigo_nav` indirectly through dynamic pressure, not as an
  explicit `$POV,S,<tas>` field. `xcvario_adapter.publish_snapshot()` computes dynamic pressure from
  `OwnshipState.speed_kmh`; `nmea.build_pxcv()` and `nmea.build_pov()` emit it as `Q`. During the
  initial `glider_launch` `ground_hold` segment, `presets.build_glider_launch_sequence()` sets
  `target_speed_kmh=0.0` and `on_ground=True`, so the emitted dynamic pressure is `Q,0.0`; later
  acceleration/climb segments emit positive `Q` as `speed_kmh` rises. If manual `glider_launch`
  keeps `speed_kmh=0.0`, the model can leave `on_ground` while airspeed remains zero; GPS output may
  then show wind-drift ground speed while air-data remains `Q,0.0`. Consumers expecting explicit
  `$POV,S` will not receive it from this simulator unless `build_pov()` is extended.
- `XcvarioTcpAdapter.publish_snapshot()` emits `$LXWP0` on the XCVario primary stream in addition to
  `$PXCV`/`$POV`/`$WIMWV`. The XCVario driver in `kigo_nav` ignores `LXWP0`, but the LX driver reads
  its vario field with `ProvideTotalEnergyVario()`. This keeps the `Vario` navbox alive when a
  profile accidentally uses `DeviceA="LX"` against the XCvario endpoint.
- Task declaration and recorded-flight readout are modeled with
  `flarm_passthrough.FlarmPassthroughSimulator`. Both `xcvario_adapter.XcvarioTcpAdapter` and
  `flarm_adapter.FlarmTcpAdapter` delegate incoming `PFLAC` text commands and `$PFLAX` binary logger
  frames to it, so declarations work whether the client targets the XCVario passthrough endpoint or
  the separate FLARM endpoint. Ordinary `$PXCV`/`$POV`/GPS/wind telemetry continues on the XCVario
  stream, and traffic `$PFLAU`/`$PFLAA` continues on the FLARM stream. The passthrough stores the
  latest declaration fields/waypoints. Logger records are loaded from sibling `../kigo_nav/logs/*.igc`
  when present; because that directory may be empty in a clean checkout, packaged fixtures live in
  `kigo_xcvario_simulator/examples/igc_logs` and are included through `pyproject.toml` package data.
  `FlarmPassthroughSimulator` derives FLARM record-list info from `HFDTE` and first/last `B` records,
  including filename, date, start time, duration, pilot, competition ID and class.
- `$PXCV` supports XCVario AHRS fields after dynamic pressure. `nmea.build_pxcv()` accepts an
  optional `roll_angle_deg`; `xcvario_adapter.publish_snapshot()` fills it only while the ownship
  phase is `circling_left` or `circling_right`. The simulated circling bank magnitude follows a
  smooth sinusoid between `35` and `50` degrees over an `8 s` period, with negative roll for left
  turns and positive roll for right turns. Pitch and acceleration fields remain empty.
- Manual `straight` mode treats `FlightDirective.baro_altitude_m` as an immediate GPS/baro altitude
  target, clamped to home altitude, so the panel `Flight Altitude [m]` field has an instant visible
  effect after `Apply Manual Mode`. After the first target application, `straight` uses a seeded
  `60 s` sinusoidal vertical-speed cycle only when `climb_min_ms`/`climb_max_ms` is provided by the
  panel/API. Those values are taken from the visible `Climb Min [m/s]` and `Climb Max [m/s]` fields;
  blank fields keep level flight, and setting both to `0` also keeps level flight. The straight-mode
  sinusoid starts near the midpoint, reaches the maximum at `15 s`, the midpoint at `30 s`, the
  minimum at `45 s`, and the midpoint again at `60 s`. A small deterministic jitter is added and
  clamped inside the configured range. The panel posts climb fields for `straight`, `circling_left`,
  `circling_right`, and `glider_launch` when they contain operator-entered values.
- FLARM traffic identity comes from `traffic_database.FLARM_TRAFFIC_AIRCRAFT`: the first six
  records are decoded FLARMNet IDs `DDA857`, `DDA85A`, `DDA85C`, `DDA86A`, `DDA88F` and `DDA896`,
  followed by 23 authentic FLARMnet-backed records with non-empty competition IDs.
  `traffic_aircraft_for()` maps by contact index so those first six IDs remain stable regardless of
  the simulation seed. The six decoded records use metadata `MF`/`D-6676`/`LS-4`,
  `L1`/`D-3450`/`Discus 2`, `TH`/`D-4449`/`Hornet`, `1A`/`D-3358`/`LS-4`,
  empty-callsign/`DKERO`/`DG-800`, and `TH`/`D-5799`/`ASK-13`. `TrafficGenerator` keeps all
  generated default contacts between 5 km and 30 km at the traffic start anchor. After the first
  traffic step, contact motion is maintained in an anchor-local north/east coordinate system and
  `$PFLAA` relative offsets are derived by subtracting the current ownship offset from that start
  anchor; later ownship movement does not drag the simulated traffic paths. Each default orbiting
  contact follows a seed/index-stable, slightly elliptical path with reported tangential speed
  between `0.5` and `5.0 m/s`. In orbit mode a contact climbs by a deterministic `300` to `1000 m`
  target, using positive climb between `0.51` and `4.0 m/s`; after reaching that target it flies a
  straight leg for `120 s` with reported climb `0.0 m/s`, then starts the next climbing orbit cycle.
  Default orbit periods are at least `2 min`. `TrafficConfig.motion_mode` accepts `orbit` (default)
  or `straight`; `/api/v1/simulation/traffic` stores it and `TrafficGenerator.step()` starts both
  modes from the same 5-30 km distance envelope. `TrafficConfig.circling_radius_min_m` and
  `circling_radius_max_m` default to `100` and `700`; the traffic generator clamps requested values
  to the usable 5-30 km envelope and picks a deterministic seed/index-stable random maximum ellipse
  radius in that range for every orbiting contact. The panel Traffic section has `Circling Radius
  Min/Max [m]` inputs and a `Traffic: Orbiting` / `Traffic: Straight` toggle that post the updated
  traffic config immediately. The optional collision-course override still replaces contact `0` with
  a converging track. `ScenarioOrchestrator` defaults traffic to enabled with all 29 contacts, and the
  control API uses the same full count when `/api/v1/simulation/traffic` enables traffic without an
  explicit `contact_count`.
  `$PFLAA`/`$PFLAU` emit the configured FLARM device ID in `aircraft_id`; the control API and panel
  additionally expose `competition_id`, `registration`, `aircraft_model` and `speed_ms`. The panel
  traffic table labels `aircraft_id` as `ID`, labels `competition_id` as `CALL SIGN` with
  registration fallback, computes horizontal distance from relative north/east offsets, and shows
  `climb_ms` as the vertical movement value.
- Start-airport placement is session-local. The panel `Connection` section stores the optional
  `Start airport or place` field in local browser storage and posts it to
  `/api/v1/simulation/start-airport` during `Connect`. Four-character ICAO values use
  `AirportLookup.find_by_icao()`, which searches local OpenAIP `*_apt.json` files, preferring sibling
  `Kigo/appdata/openaip` from the runtime working tree, with built-in fallback positions for `FWCT`
  and `KMEV`. Non-ICAO values use the configured Nominatim-compatible online geocoder endpoint
  (`KIGO_GEOCODER_SEARCH_URL`, default `https://nominatim.openstreetmap.org/search`) with
  `format=jsonv2`, `limit=1`, a custom User-Agent (`KIGO_GEOCODER_USER_AGENT` override), and optional
  `countrycodes` inferred from the free-text suffix. Geocoded results are cached as
  `geocode:<normalized-query>` in `.cache/airport_icao_cache.json`; because the geocoder returns
  latitude/longitude but not terrain elevation, `gps_altitude_m` is `0.0` for online results.
  `SimulatorRuntimeSession` applies the resolved coordinate through
  `ScenarioOrchestrator.set_home_position()`, which updates the in-memory `FlightModel` home, clears
  active plans/traffic, and places the ownship on the ground without modifying `runtime.local.json`; a
  runtime restart returns to the configured home position.

## Build, Run, And Test Notes

- The simulator panel is operator UI only; bridge actions are posted to the selected runtime API
  (`/api/v1/bridges/*`) and execute from that runtime host. With the default panel URL
  `http://172.16.119.137:8181`, bridge SSH and `systemd-run --user` happen on the VM, not on the
  Mac browser host. The Pi bridge default target is `admin@192.168.0.114`, identity
  `/home/slawek/.ssh/kigo_pi`, workdir `/home/admin/kigo_xcvario_simulator`, and it uses a reverse
  SSH tunnel from the runtime host to Pi for ports `4353` and `4354`.
- As of 2026-06-04, the active lab Pi address is `admin@192.168.0.106`; override stale panel/API
  bridge targets that still point at `admin@192.168.0.114`.
- The panel can run bridge control in VM-only mode when the Pi is powered off: leave the Pi bridge
  target empty so bridge API requests include only the VM node. A filled Pi target is treated as an
  explicit request to start/status that Pi and will make bridge readiness fail while the Pi is
  offline.
- As of 2026-06-07, the active VM runtime address is `172.16.119.137`; override stale panel/API
  bridge targets or SSH forwards that still point at `172.16.119.135`.
- The VM runtime is installed as an enabled user-systemd service at
  `/home/slawek/.config/systemd/user/kigo-xcvario-runtime.service`, running
  `/usr/bin/python3 -m kigo_xcvario_simulator.start_remote_runtime --config /home/slawek/kigo_xcvario_simulator/runtime.local.json`
  from `/home/slawek/kigo_xcvario_simulator`. `Connect` in the panel can restart/start bridges only
  after this runtime API is already reachable; it cannot bootstrap the runtime if the VM has no
  `kigo-xcvario-runtime.service`. Do not rely on `/tmp/runtime.local.json` after VM restarts; it may
  be missing and will put the service into an autorestart failure loop.
- For iPhone access on the local LAN, serve the panel on the Mac with `--host 0.0.0.0` and use the
  Mac LAN address, e.g. `http://192.168.0.107:8180/`. Because the iPhone cannot necessarily route to
  the VM-only `172.16.119.0/24` network, expose the runtime API through a Mac SSH local forward such
  as `0.0.0.0:8181 -> 127.0.0.1:8181` on the VM and set the panel Runtime URL to
  `http://192.168.0.107:8181`. The VM runtime config must include the panel origin
  `http://192.168.0.107:8180` in `control_api.cors_allowed_origins`. The panel derives the default
  runtime URL from the page host when it is opened from a non-localhost address, replaces stored
  private `:8181` URLs from a different private host in that LAN mode, and tries the page host on
  port `8181` plus the default runtime URL as connect fallbacks. This recovers stale self-forward URLs such as
  `http://172.20.10.4:8181` after the Mac LAN address changes. `http://172.20.10.4:8181` is also
  treated as a known stale runtime URL when the panel is opened from localhost, so reload falls back
  to the active VM runtime URL.
- On 2026-06-12 the Mac LAN panel/API address was `192.168.0.135`; add
  `http://192.168.0.135:8180` to the VM runtime `control_api.cors_allowed_origins` when serving the
  panel from that address. A healthy `curl` to `:8181` is not enough for browser access; verify CORS
  with an `OPTIONS` request carrying `Origin: http://<mac-lan-ip>:8180`.
- As of 2026-06-15, the active Pi is reachable from `codex-vm` through Tailscale as
  `kigo-pi` / `100.115.17.10`, hostname `ssdkigo1`. `codex-vm` cannot use system Tailscale without
  sudo, so it runs a rootless user service
  `/home/slawek/.config/systemd/user/tailscaled-userspace.service` with
  `tailscaled --tun=userspace-networking --socks5-server=127.0.0.1:1055` and socket
  `/home/slawek/.local/run/tailscale/tailscaled.sock`. VM SSH config alias `kigo-pi-tail` uses
  `ProxyCommand /home/slawek/.local/bin/tailscale --socket=/home/slawek/.local/run/tailscale/tailscaled.sock nc %h %p`
  plus identity `/home/slawek/.ssh/kigo_pi`; use `kigo-pi-tail` as the panel/API `PI Bridge Target`
  for outside-LAN Pi bridge control. On 2026-06-15, restarting bridges through
  `http://127.0.0.1:8181/api/v1/bridges/restart` with VM target `localhost` and Pi target
  `kigo-pi-tail` produced ready VM and Pi bridges, active Pi tunnel, and non-zero
  `primary_bytes_tcp_to_pty` / `flarm_bytes_tcp_to_pty`. Stop the VM Tailscale userspace service
  with `systemctl --user stop tailscaled-userspace.service`; stop bridge units through
  `/api/v1/bridges/stop` or manually stop `kigo-xcvario-tunnel-pi.service`,
  `kigo-xcvario-pty-xcvario.service` and `kigo-xcvario-pty-flarm.service`.
- The Android phone USB bridge lives under `android_bridge/` and is intentionally separate from the
  Python simulator package. It builds a debug-signed APK with local Android SDK tools, no Gradle:
  `./android_bridge/build_apk.sh`. The script uses `ANDROID_HOME`/`ANDROID_SDK_ROOT` or
  `$HOME/Library/Android/sdk`, and `JAVA_HOME` or the bundled JBR from Android Studio/PyCharm.
  Runtime data flow is Kigo/Nav on Android connecting to `127.0.0.1:4353`/`4354`, the APK forwarding
  those sockets to Android-local upstream
  `127.0.0.1:44353`/`44354`, and `adb reverse tcp:44353 tcp:4353` plus
  `adb reverse tcp:44354 tcp:4354` carrying the streams back to the Mac simulator. This is TCP-only;
  a normal APK cannot expose a virtual serial device to another APK without root or explicit app
  integration. The bridge service is not exported and is intentionally not sticky/autostarted;
  `install_bridge.sh` opens `MainActivity`, but the operator must press `Start` in the bridge app to
  start the foreground service.
- On the tested Android 11 Samsung device, `kigo.nav` loads the active profile from
  `/sdcard/Android/media/kigo.nav/XCSoarData/kigo_default.top`; matching-looking profiles under
  `/sdcard/Android/data/kigo.nav/files/XCSoarData` can be stale. A connection error after activating
  the APK bridge may be caused by the active profile still using `PortPath="/tmp/kigo-sim/xcvario"`
  and `Port3Path="/tmp/kigo-sim/flarm"`. Switch `PortType`/`Port3Type` to `tcp_client`, set
  `PortIPAddress`/`Port3IPAddress` to `127.0.0.1`, clear `PortPath`/`Port3Path`, and keep TCP ports
  `4353`/`4354`, then force-stop/restart Kigo.
- If Kigo crashes shortly after opening the Android setup/Advanced flow while the phone bridge is
  active, first check whether the `Raw Logger` / `Logger nmea` action was hit or NMEA logging was
  enabled. The 2026-06-18 Samsung A50 crash was a `kigo.nav` native abort in `IOThread`, not a bridge
  process crash: `DeviceDescriptor::LineReceived()` called `NMEALogger::Log()`, which allocated
  `TextWriter("logs/<timestamp>.nmea")`; file open failed and `TextWriter::Write()` asserted
  `file.IsOpen()`. Symbolicate installed `libkigo.so` offsets with
  `$ANDROID_HOME/ndk/26.3.11579264/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-addr2line -Cf -e ../kigo_nav/output/ANDROIDAARCH64/bin/libkigo-ns.so <offsets>`.

## Important Files And Ownership

_To be filled as durable knowledge is discovered._

## Debugging Notes And Gotchas

- A circling ground trace with wind should drift from the first simulated tick; the simulator does
  not store or redraw historical trail points. If a displayed old trail immediately changes shape
  after updating wind, suspect the consumer's trail rendering/wind-drift compensation rather than
  historical position output from this simulator.
- TCP-to-PTY bridge control uses transient user-systemd units:
  `kigo-xcvario-pty-xcvario.service`, `kigo-xcvario-pty-flarm.service`, and for Pi
  `kigo-xcvario-tunnel-pi.service`. Status JSON lives under `/tmp/kigo-sim/*.status.json`, while
  bridge logs are appended in the remote workdir (`pty-xcvario-to-mac.log`,
  `pty-flarm-to-mac.log`) and the Pi tunnel log is `/tmp/kigo-sim/kigo-xcvario-tunnel-pi.log` on
  the runtime host. `systemctl --user is-active kigo-xcvario-tunnel-pi.service` can report
  `active` while SSH is repeatedly timing out or restarting; inspect the tunnel log or
  `systemctl --user status ...` restart counter before treating it as a healthy tunnel.
- If XCSoar reports `GPS waiting for fix` while the control API says the runtime is `running`, check
  the `snapshot.ownship.timestamp_utc`, `runtime.scheduler.last_error`, and bridge byte counters. On
  2026-06-12 the runtime API stayed live with a stale 2026-06-11 snapshot after the telemetry
  scheduler thread crashed on `ValueError: Invalid QNH/altitude combination for pressure conversion`.
  The VM bridge could be `active/tcp` but `primary_bytes_tcp_to_pty` stayed at zero until the runtime
  service was restarted. Recovery was: restart `kigo-xcvario-runtime.service`, re-apply manual mode,
  restart the VM bridge, then verify `$GPRMC`/`$GPGGA` output with `nc 127.0.0.1 4353` on the VM.
- As of 2026-06-12, `admin@192.168.0.111` is not a usable Pi bridge target for this lab setup: from
  the VM it presents a changed host key relative to `/home/slawek/.ssh/known_hosts`, and with a clean
  temporary known-hosts file it still rejects `/home/slawek/.ssh/kigo_pi`. Do not clear the stale
  known-hosts entry as a bridge fix unless the device identity and authorized key are verified first.
  `192.168.0.106`, `192.168.0.108`, and `192.168.0.113` timed out for SSH in the same check.

## Decisions And Assumptions

_To be filled as durable knowledge is discovered._

## Change Log Of Documentation Updates

- 2026-05-29: Created project documentation discipline and initial technical memory file.
- 2026-05-29: Documented ownship wind-vector flow and the circling-trail diagnostic gotcha.
- 2026-06-01: Documented XCVario airspeed output as dynamic-pressure `Q` rather than explicit
  `$POV,S`, including zero-speed `glider_launch` ground-hold / wind-drift behavior.
- 2026-06-03: Documented XCvario-to-IGC-FLARM passthrough support for declaration and synthetic
  recorded-flight download.
- 2026-06-03: Documented synthetic XCVario AHRS roll output during circling.
- 2026-06-03: Documented IGC logger sample loading from `../kigo_nav/logs` with packaged fixture fallback.
- 2026-06-03: Documented direct FLARM endpoint declaration/logger support in addition to XCVario passthrough.
- 2026-06-03: Documented manual straight-mode climb/sink behavior using frontend climb min/max.
- 2026-06-04: Documented XCVario-stream `LXWP0` compatibility fallback for `kigo_nav` vario navbox.
- 2026-06-03: Documented bridge-control execution host, user-systemd units, status/log locations,
  and reverse-tunnel active-state gotcha.
- 2026-06-18: Documented Android phone bridge crash triage showing Kigo NMEA logger/TextWriter as
  the failing path, not the bridge APK process.
- 2026-06-04: Documented active lab Pi bridge address and transient VM runtime service using the
  durable VM-local runtime config path.
- 2026-06-05: Documented iPhone/LAN panel access via Mac LAN address, CORS origin, and Mac-to-VM
  runtime API forwarding.
- 2026-06-05: Documented LAN-mode panel default runtime URL behavior for stale VM runtime URLs.
- 2026-06-05: Documented that panel Connect depends on an already-running runtime API and that the
  VM runtime now uses an enabled persistent user-systemd service instead of a transient unit.
- 2026-06-05: Documented smooth manual `straight` altitude-target ramping instead of immediate
  GPS/baro altitude jumps. Superseded on 2026-06-08.
- 2026-06-06: Documented fixed `0.1 m/s` manual `straight` altitude-target ramp rate. Superseded on
  2026-06-08.
- 2026-06-06: Documented empty default manual climb fields in the panel to avoid accidental
  post-target climb in `straight`.
- 2026-06-06: Documented one-minute sinusoidal manual `straight` climb variation and panel posting
  of explicit `Climb Min/Max` values for `straight`.
- 2026-06-06: Documented FLARMnet-backed traffic IDs and competition-sign metadata.
- 2026-06-06: Documented the reduced three-ID lab FLARM traffic database.
- 2026-06-07: Documented 26-contact FLARM traffic rings, rotating lab-ID collision course, and
  current VM runtime address `172.16.119.137`.
- 2026-06-08: Documented default all-contact FLARM traffic generation within 40 km, two circling
  contacts, linear movement for the remaining contacts, real metadata for the first six IDs, and
  speed output.
- 2026-06-08: Documented the full six decoded FLARMNet IDs in the simulator traffic set and the
  resulting 29-contact default.
- 2026-06-08: Documented VM-only bridge control by leaving the Pi bridge target empty while the Pi is
  powered off.
- 2026-06-08: Documented traffic-table ID, call sign, distance and vertical movement columns.
- 2026-06-08: Documented LAN-mode runtime URL recovery from stale private self-forward hosts.
- 2026-06-08: Documented localhost-mode recovery from the stale `172.20.10.4:8181` runtime URL.
- 2026-06-08: Documented default-runtime connect fallback for stale runtime URL entries.
- 2026-06-08: Documented immediate manual `straight` altitude application from the panel.
- 2026-06-12: Documented stale-live runtime diagnosis, CORS update for Mac LAN `192.168.0.135`, and
  the current unusable `admin@192.168.0.111` Pi bridge target symptoms.
- 2026-06-12: Documented session-local start-airport ICAO placement and `.cache/airport_icao_cache.json`.
- 2026-06-13: Documented the built-in `FWCT` Worcester start-position alias.
- 2026-06-15: Documented rootless Tailscale access from `codex-vm` to the active Pi and the
  `kigo-pi-tail` bridge target.
- 2026-06-18: Documented start-airport lookup accepting ICAO through local OpenAIP and non-ICAO
  free-text place/country queries through a configurable online geocoder.
- 2026-06-18: Documented default FLARM traffic orbiting within 100 km at `0.5` to `5.0 m/s`
  tangential speed. Superseded later the same day by the 5-30 km traffic-distance range.
- 2026-06-18: Documented default FLARM traffic staying 5-30 km from ownship, with at least four
  climbing orbit contacts and orbit periods of at least `2 min`.
- 2026-06-18: Documented that every default orbiting FLARM contact uses a positive `0.51` to
  `4.0 m/s` climb range.
- 2026-06-18: Documented the Android phone USB bridge APK and its `adb reverse` TCP data path.
- 2026-06-18: Documented that Android bridge activation is manual through `MainActivity`, not an
  exported service or autostart.
- 2026-06-18: Documented Android Kigo active profile location under `Android/media` and the
  serial-to-TCP profile fix needed for the USB bridge.
- 2026-06-19: Documented `straight` vario oscillation using the panel/API `Climb Min/Max` bounds with
  small deterministic jitter.
- 2026-06-19: Documented the FLARM traffic `motion_mode` API and panel toggle for `orbit` versus
  `straight` contact movement.
- 2026-06-19: Documented FLARM traffic circling radius min/max API and panel inputs, with per-contact
  deterministic radius selection.
- 2026-06-19: Documented start-anchored FLARM traffic, elliptical climbing orbit cycles, and 120 s
  straight legs after each 300-1000 m orbit climb.
