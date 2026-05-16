"""Runtime wiring for the simulator core without UI concerns."""

from __future__ import annotations

from threading import Lock

from .config import SimulatorRuntimeConfig, normalize_primary_device
from .contracts import ManualModeInput, PresetRequest, SimulationSnapshot
from .flarm_adapter import FlarmTcpAdapter
from .orchestrator import ScenarioOrchestrator
from .scheduler import TelemetryScheduler
from .state import FlightPhase
from .sxhawk_adapter import SxHawkTcpAdapter
from .xcvario_adapter import DEFAULT_OAT_C, XcvarioTcpAdapter, validate_oat_c
from .xcvario_polar import get_xcvario_polar


class SimulatorRuntimeSession:
    def __init__(
        self,
        runtime_config: SimulatorRuntimeConfig,
        *,
        orchestrator: ScenarioOrchestrator | None = None,
        xcvario_adapter=None,
        sxhawk_adapter=None,
        flarm_adapter=None,
        scheduler: TelemetryScheduler | None = None,
    ) -> None:
        self.runtime_config = runtime_config
        self.orchestrator = orchestrator or ScenarioOrchestrator(runtime_config)
        self._primary_lock = Lock()
        self._primary_device = normalize_primary_device(runtime_config.primary_device)
        xcvario_polar = get_xcvario_polar(runtime_config.xcvario.polar_name)
        self.xcvario_adapter = xcvario_adapter or XcvarioTcpAdapter(
            bind_host=runtime_config.xcvario.bind_host,
            port=runtime_config.xcvario.port,
            polar=xcvario_polar,
            on_qnh_command=self.set_device_qnh_hpa,
            on_altitude_command=self.set_device_altitude_m,
            on_client_connect=self.activate_on_ground_default,
            gps_every_baro_frames=_gps_every_baro_frames(
                gps_hz=runtime_config.scheduler.gps_hz,
                baro_hz=runtime_config.scheduler.baro_hz or runtime_config.scheduler.ownship_hz,
            ),
        )
        self.sxhawk_adapter = sxhawk_adapter or SxHawkTcpAdapter(
            bind_host=runtime_config.xcvario.bind_host,
            port=runtime_config.xcvario.port,
            polar=xcvario_polar,
            on_qnh_command=self.set_device_qnh_hpa,
            on_altitude_command=self.set_device_altitude_m,
            on_client_connect=self.activate_on_ground_default,
            gps_every_baro_frames=_gps_every_baro_frames(
                gps_hz=runtime_config.scheduler.gps_hz,
                baro_hz=runtime_config.scheduler.baro_hz or runtime_config.scheduler.ownship_hz,
            ),
        )
        self._primary_adapters = {
            "xcvario": self.xcvario_adapter,
            "sxhawk": self.sxhawk_adapter,
        }
        self.flarm_adapter = flarm_adapter or FlarmTcpAdapter(
            bind_host=runtime_config.flarm.bind_host,
            port=runtime_config.flarm.port,
        )
        self._oat_c = float(getattr(self._active_primary_adapter(), "oat_c", DEFAULT_OAT_C))
        self.scheduler = scheduler or TelemetryScheduler(
            orchestrator=self.orchestrator,
            ownship_publishers=(self,),
            traffic_publishers=(self.flarm_adapter,),
            tick_hz=runtime_config.scheduler.tick_hz,
            ownship_hz=runtime_config.scheduler.baro_hz or runtime_config.scheduler.ownship_hz,
            traffic_hz=runtime_config.scheduler.traffic_hz,
        )
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    @property
    def primary_device(self) -> str:
        with self._primary_lock:
            return self._primary_device

    def start(self, *, start_scheduler: bool = True) -> None:
        if self._started:
            return
        primary_adapter = self._active_primary_adapter()
        if hasattr(primary_adapter, "start"):
            primary_adapter.start()
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
        for adapter in self._unique_primary_adapters():
            if hasattr(adapter, "stop"):
                adapter.stop()
        self._started = False

    def publish_snapshot(self, snapshot: SimulationSnapshot) -> None:
        adapter = self._active_primary_adapter()
        publisher = getattr(adapter, "publish_snapshot", None)
        if callable(publisher):
            publisher(snapshot)

    def add_snapshot_listener(self, listener) -> None:
        self.scheduler.add_snapshot_listener(listener)

    def remove_snapshot_listener(self, listener) -> None:
        self.scheduler.remove_snapshot_listener(listener)

    def get_snapshot(self) -> SimulationSnapshot:
        return self.orchestrator.get_snapshot()

    def get_runtime_metadata(self) -> dict[str, object]:
        traffic_config = self.orchestrator.get_traffic_config()
        wind = self.orchestrator.get_wind()
        snapshot = self.orchestrator.get_snapshot()
        primary_device = self.primary_device
        return {
            "session_id": self.runtime_config.session_id,
            "started": self._started,
            "seed": snapshot.seed,
            "primary_device": primary_device,
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
                "static_pressure_hpa": snapshot.ownship.static_pressure_hpa,
                "device_qnh_hpa": snapshot.ownship.device_qnh_hpa,
                "device_altitude_m": snapshot.ownship.device_altitude_m,
            },
            "adapters": {
                "xcvario": {
                    "bound_port": getattr(self.xcvario_adapter, "bound_port", self.runtime_config.xcvario.port),
                    "client_connected": bool(getattr(self.xcvario_adapter, "client_connected", False)),
                    "polar_name": self.runtime_config.xcvario.polar_name,
                    "active": primary_device == "xcvario",
                },
                "sxhawk": {
                    "bound_port": getattr(self.sxhawk_adapter, "bound_port", self.runtime_config.xcvario.port),
                    "client_connected": bool(getattr(self.sxhawk_adapter, "client_connected", False)),
                    "polar_name": self.runtime_config.xcvario.polar_name,
                    "active": primary_device == "sxhawk",
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
        for adapter in self._unique_primary_adapters():
            setter = getattr(adapter, "set_oat_c", None)
            if callable(setter):
                setter(resolved_oat_c)
        self._oat_c = resolved_oat_c
        return self.orchestrator.get_snapshot()

    def set_device_qnh_hpa(self, qnh_hpa: float) -> SimulationSnapshot:
        return self.orchestrator.set_device_qnh_hpa(qnh_hpa)

    def set_device_altitude_m(self, altitude_m: float) -> SimulationSnapshot:
        return self.orchestrator.set_device_altitude_m(altitude_m)

    def set_primary_device(self, primary_device: str) -> SimulationSnapshot:
        resolved_device = normalize_primary_device(primary_device)
        with self._primary_lock:
            previous_device = self._primary_device
            if previous_device == resolved_device:
                return self.orchestrator.get_snapshot()
            previous_adapter = self._primary_adapters[previous_device]
            next_adapter = self._primary_adapters[resolved_device]
            was_started = self._started
            if was_started and hasattr(previous_adapter, "stop"):
                previous_adapter.stop()
            setter = getattr(next_adapter, "set_oat_c", None)
            if callable(setter):
                setter(self._oat_c)
            self._primary_device = resolved_device
            if was_started and hasattr(next_adapter, "start"):
                next_adapter.start()
        return self.orchestrator.get_snapshot()

    def _active_primary_adapter(self):
        with self._primary_lock:
            return self._primary_adapters[self._primary_device]

    def _unique_primary_adapters(self):
        seen: set[int] = set()
        adapters = []
        for adapter in self._primary_adapters.values():
            marker = id(adapter)
            if marker in seen:
                continue
            seen.add(marker)
            adapters.append(adapter)
        return tuple(adapters)


def _gps_every_baro_frames(*, gps_hz: int, baro_hz: int) -> int:
    return max(1, round(max(1, int(baro_hz)) / max(1, int(gps_hz))))
