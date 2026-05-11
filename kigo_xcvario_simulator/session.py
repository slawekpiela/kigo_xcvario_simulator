"""Runtime wiring for the simulator core without UI concerns."""

from __future__ import annotations

from .config import SimulatorRuntimeConfig
from .contracts import ManualModeInput, PresetRequest, SimulationSnapshot
from .flarm_adapter import FlarmTcpAdapter
from .orchestrator import ScenarioOrchestrator
from .scheduler import TelemetryScheduler
from .state import FlightPhase
from .xcvario_adapter import DEFAULT_OAT_C, XcvarioTcpAdapter, validate_oat_c
from .xcvario_polar import get_xcvario_polar


class SimulatorRuntimeSession:
    def __init__(
        self,
        runtime_config: SimulatorRuntimeConfig,
        *,
        orchestrator: ScenarioOrchestrator | None = None,
        xcvario_adapter=None,
        flarm_adapter=None,
        scheduler: TelemetryScheduler | None = None,
    ) -> None:
        self.runtime_config = runtime_config
        self.orchestrator = orchestrator or ScenarioOrchestrator(runtime_config)
        xcvario_polar = get_xcvario_polar(runtime_config.xcvario.polar_name)
        self.xcvario_adapter = xcvario_adapter or XcvarioTcpAdapter(
            bind_host=runtime_config.xcvario.bind_host,
            port=runtime_config.xcvario.port,
            polar=xcvario_polar,
            on_qnh_command=self.set_device_qnh_hpa,
            on_client_connect=self.activate_on_ground_default,
            gps_every_baro_frames=_gps_every_baro_frames(
                gps_hz=runtime_config.scheduler.gps_hz,
                baro_hz=runtime_config.scheduler.baro_hz or runtime_config.scheduler.ownship_hz,
            ),
        )
        self.flarm_adapter = flarm_adapter or FlarmTcpAdapter(
            bind_host=runtime_config.flarm.bind_host,
            port=runtime_config.flarm.port,
        )
        self._oat_c = float(getattr(self.xcvario_adapter, "oat_c", DEFAULT_OAT_C))
        self.scheduler = scheduler or TelemetryScheduler(
            orchestrator=self.orchestrator,
            ownship_publishers=(self.xcvario_adapter,),
            traffic_publishers=(self.flarm_adapter,),
            tick_hz=runtime_config.scheduler.tick_hz,
            ownship_hz=runtime_config.scheduler.baro_hz or runtime_config.scheduler.ownship_hz,
            traffic_hz=runtime_config.scheduler.traffic_hz,
        )
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def start(self, *, start_scheduler: bool = True) -> None:
        if self._started:
            return
        if hasattr(self.xcvario_adapter, "start"):
            self.xcvario_adapter.start()
        if hasattr(self.flarm_adapter, "start"):
            self.flarm_adapter.start()
        if start_scheduler:
            self.scheduler.start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self.scheduler.stop()
        if hasattr(self.flarm_adapter, "stop"):
            self.flarm_adapter.stop()
        if hasattr(self.xcvario_adapter, "stop"):
            self.xcvario_adapter.stop()
        self._started = False

    def add_snapshot_listener(self, listener) -> None:
        self.scheduler.add_snapshot_listener(listener)

    def remove_snapshot_listener(self, listener) -> None:
        self.scheduler.remove_snapshot_listener(listener)

    def get_snapshot(self) -> SimulationSnapshot:
        return self.orchestrator.get_snapshot()

    def get_runtime_metadata(self) -> dict[str, object]:
        traffic_config = self.orchestrator.get_traffic_config()
        wind = self.orchestrator.get_wind()
        return {
            "session_id": self.runtime_config.session_id,
            "started": self._started,
            "seed": self.orchestrator.get_snapshot().seed,
            "scheduler": {
                "tick_count": self.scheduler.tick_count,
                "last_jitter_s": self.scheduler.last_jitter_s,
                "gps_hz": self.runtime_config.scheduler.gps_hz,
                "baro_hz": self.runtime_config.scheduler.baro_hz or self.runtime_config.scheduler.ownship_hz,
                "traffic_hz": self.runtime_config.scheduler.traffic_hz,
            },
            "traffic_config": {
                "enabled": traffic_config.enabled,
                "contact_count": traffic_config.contact_count,
                "collision_course": traffic_config.collision_course,
            },
            "wind": {
                "direction_deg": wind.direction_deg,
                "speed_kmh": wind.speed_kmh,
            },
            "environment": {
                "oat_c": self._oat_c,
            },
            "adapters": {
                "xcvario": {
                    "bound_port": getattr(self.xcvario_adapter, "bound_port", self.runtime_config.xcvario.port),
                    "client_connected": bool(getattr(self.xcvario_adapter, "client_connected", False)),
                    "polar_name": self.runtime_config.xcvario.polar_name,
                },
                "flarm": {
                    "bound_port": getattr(self.flarm_adapter, "bound_port", self.runtime_config.flarm.port),
                    "client_connected": bool(getattr(self.flarm_adapter, "client_connected", False)),
                },
            },
        }

    def start_simulation(self) -> SimulationSnapshot:
        return self.orchestrator.start()

    def pause_simulation(self) -> SimulationSnapshot:
        return self.orchestrator.pause()

    def reset_simulation(self) -> SimulationSnapshot:
        return self.orchestrator.reset()

    def load_preset(self, request: PresetRequest, *, overrides: dict[str, object] | None = None) -> SimulationSnapshot:
        return self.orchestrator.load_preset(request, overrides=overrides)

    def activate_on_ground_default(self) -> SimulationSnapshot:
        self.orchestrator.reset()
        self.orchestrator.set_manual_mode(
            ManualModeInput(
                phase=FlightPhase.GLIDER_LAUNCH,
                speed_kmh=0.0,
                on_ground=True,
            )
        )
        return self.orchestrator.start()

    def set_manual_mode(self, manual_input: ManualModeInput) -> SimulationSnapshot:
        return self.orchestrator.set_manual_mode(manual_input)

    def set_traffic_config(
        self,
        enabled: bool,
        contact_count: int,
        collision_course: bool = False,
    ) -> SimulationSnapshot:
        return self.orchestrator.set_traffic_config(enabled, contact_count, collision_course)

    def set_wind(self, direction_deg: float, speed_kmh: float) -> SimulationSnapshot:
        return self.orchestrator.set_wind(direction_deg, speed_kmh)

    def set_oat_c(self, oat_c: float) -> SimulationSnapshot:
        resolved_oat_c = validate_oat_c(oat_c)
        setter = getattr(self.xcvario_adapter, "set_oat_c", None)
        if callable(setter):
            setter(resolved_oat_c)
        self._oat_c = resolved_oat_c
        return self.orchestrator.get_snapshot()

    def set_device_qnh_hpa(self, qnh_hpa: float) -> SimulationSnapshot:
        return self.orchestrator.set_device_qnh_hpa(qnh_hpa)


def _gps_every_baro_frames(*, gps_hz: int, baro_hz: int) -> int:
    return max(1, round(max(1, int(baro_hz)) / max(1, int(gps_hz))))
