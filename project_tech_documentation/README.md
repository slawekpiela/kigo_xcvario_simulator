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
- Manual `straight` mode has two altitude behaviors. Without `climb_min_ms`/`climb_max_ms`, a
  `FlightDirective.baro_altitude_m` pins GPS altitude and static pressure to the requested manual
  altitude on every tick. When a climb range is present, `baro_altitude_m` is only the starting
  altitude applied when the directive first becomes active; subsequent ticks update GPS altitude and
  pressure from a smooth oscillating vertical speed between the configured climb min/max. The panel
  sends the visible `Climb Min [m/s]` and `Climb Max [m/s]` fields for `straight`,
  `circling_left`, and `circling_right`.

## Build, Run, And Test Notes

_To be filled as durable knowledge is discovered._

## Important Files And Ownership

_To be filled as durable knowledge is discovered._

## Debugging Notes And Gotchas

- A circling ground trace with wind should drift from the first simulated tick; the simulator does
  not store or redraw historical trail points. If a displayed old trail immediately changes shape
  after updating wind, suspect the consumer's trail rendering/wind-drift compensation rather than
  historical position output from this simulator.

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
