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
- Manual `straight` mode treats `FlightDirective.baro_altitude_m` as a smooth target altitude, not
  an immediate GPS/baro pin. The flight model ramps from the current altitude to that target,
  clamped to home altitude, at a fixed `0.1 m/s`. After the target is reached, no climb range means
  level flight at the target; a climb range resumes the smooth oscillating vertical speed between
  the configured climb min/max as a sinusoid with a full `60 s` cycle. The sinusoid starts at the
  configured minimum, reaches the midpoint at `15 s`, the maximum at `30 s`, the midpoint at
  `45 s`, and returns to the minimum at `60 s`. `climb_min_ms`/`climb_max_ms` do not speed up the
  initial target ramp. The panel leaves the visible `Climb Min [m/s]` and `Climb Max [m/s]` fields
  empty by default, but posts them for `straight`, `circling_left`, `circling_right`, and
  `glider_launch` when they contain operator-entered values.
- FLARM traffic identity comes from `traffic_database.FLARM_TRAFFIC_AIRCRAFT`, a curated FLARMnet
  DDB sample downloaded from `https://www.flarmnet.org/files/ddb.json` on 2026-06-06. Records were
  filtered to identified/tracked `device_type="F"` devices with six-hex-digit IDs, Polish
  registrations and non-empty alphanumeric competition IDs. `TrafficGenerator` assigns records
  deterministically from the simulation seed and contact index. `$PFLAA`/`$PFLAU` still emit the
  real FLARM device ID in `aircraft_id`; the control API and panel additionally expose
  `competition_id`, `registration` and `aircraft_model`.

## Build, Run, And Test Notes

- The simulator panel is operator UI only; bridge actions are posted to the selected runtime API
  (`/api/v1/bridges/*`) and execute from that runtime host. With the default panel URL
  `http://172.16.119.135:8181`, bridge SSH and `systemd-run --user` happen on the VM, not on the
  Mac browser host. The Pi bridge default target is `admin@192.168.0.114`, identity
  `/home/slawek/.ssh/kigo_pi`, workdir `/home/admin/kigo_xcvario_simulator`, and it uses a reverse
  SSH tunnel from the runtime host to Pi for ports `4353` and `4354`.
- As of 2026-06-04, the active lab Pi address is `admin@192.168.0.106`; override stale panel/API
  bridge targets that still point at `admin@192.168.0.114`.
- The VM runtime is installed as an enabled user-systemd service at
  `/home/slawek/.config/systemd/user/kigo-xcvario-runtime.service`, running
  `/usr/bin/python3 -m kigo_xcvario_simulator.start_remote_runtime --config /home/slawek/kigo_xcvario_simulator/runtime.local.json`
  from `/home/slawek/kigo_xcvario_simulator`. `Connect` in the panel can restart/start bridges only
  after this runtime API is already reachable; it cannot bootstrap the runtime if the VM has no
  `kigo-xcvario-runtime.service`. Do not rely on `/tmp/runtime.local.json` after VM restarts; it may
  be missing and will put the service into an autorestart failure loop.
- For iPhone access on the local LAN, serve the panel on the Mac with `--host 0.0.0.0` and use the
  Mac LAN address, e.g. `http://192.168.0.107:8180/`. Because the iPhone cannot necessarily route to
  the VM-only `172.16.119.135` network, expose the runtime API through a Mac SSH local forward such
  as `0.0.0.0:8181 -> 127.0.0.1:8181` on the VM and set the panel Runtime URL to
  `http://192.168.0.107:8181`. The VM runtime config must include the panel origin
  `http://192.168.0.107:8180` in `control_api.cors_allowed_origins`. The panel derives the default
  runtime URL from the page host when it is opened from a non-localhost address and replaces stale
  stored `http://172.16.119.135:8181` values in that LAN mode.

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
- 2026-06-04: Documented active lab Pi bridge address and transient VM runtime service using the
  durable VM-local runtime config path.
- 2026-06-05: Documented iPhone/LAN panel access via Mac LAN address, CORS origin, and Mac-to-VM
  runtime API forwarding.
- 2026-06-05: Documented LAN-mode panel default runtime URL behavior for stale VM runtime URLs.
- 2026-06-05: Documented that panel Connect depends on an already-running runtime API and that the
  VM runtime now uses an enabled persistent user-systemd service instead of a transient unit.
- 2026-06-05: Documented smooth manual `straight` altitude-target ramping instead of immediate
  GPS/baro altitude jumps.
- 2026-06-06: Documented fixed `0.1 m/s` manual `straight` altitude-target ramp rate.
- 2026-06-06: Documented empty default manual climb fields in the panel to avoid accidental
  post-target climb in `straight`.
- 2026-06-06: Documented one-minute sinusoidal manual `straight` climb variation and panel posting
  of explicit `Climb Min/Max` values for `straight`.
- 2026-06-06: Documented FLARMnet-backed traffic IDs and competition-sign metadata.
