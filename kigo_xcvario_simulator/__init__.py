"""Core modules for the XCvario simulator."""

from .config import (
    DEFAULT_CONTROL_API_PORT,
    DEFAULT_FLARM_PORT,
    DEFAULT_XCVARIO_PORT,
    SimulatorRuntimeConfig,
    XcvarioConfig,
    load_runtime_config,
)
from .control_api import ControlApiServer
from .contracts import (
    FlightDirective,
    ManualModeInput,
    OwnshipState,
    PresetPlan,
    PresetRequest,
    SimulationSnapshot,
    TrafficConfig,
    TrafficContact,
    WindState,
)
from .flarm_adapter import FlarmTcpAdapter
from .flight_model import FlightModel
from .nmea import build_gpgga, build_gprmc, build_pflaa, build_pflau, build_pov, build_pxcv, build_wimwv
from .orchestrator import ScenarioOrchestrator
from .scheduler import TelemetryScheduler
from .session import SimulatorRuntimeSession
from .state import FlightPhase, HealthState, RuntimeState
from .traffic_model import TrafficGenerator
from .xcvario_adapter import XcvarioTcpAdapter
from .xcvario_polar import XCVARIO_POLARS, XcvarioPolar, get_xcvario_polar

__all__ = [
    "ControlApiServer",
    "DEFAULT_CONTROL_API_PORT",
    "DEFAULT_FLARM_PORT",
    "DEFAULT_XCVARIO_PORT",
    "FlightDirective",
    "FlightModel",
    "FlightPhase",
    "HealthState",
    "ManualModeInput",
    "OwnshipState",
    "PresetPlan",
    "PresetRequest",
    "RuntimeState",
    "ScenarioOrchestrator",
    "SimulationSnapshot",
    "SimulatorRuntimeConfig",
    "SimulatorRuntimeSession",
    "TelemetryScheduler",
    "TrafficConfig",
    "TrafficContact",
    "TrafficGenerator",
    "WindState",
    "FlarmTcpAdapter",
    "XcvarioTcpAdapter",
    "XCVARIO_POLARS",
    "XcvarioConfig",
    "XcvarioPolar",
    "build_gpgga",
    "build_gprmc",
    "build_pflaa",
    "build_pflau",
    "build_pov",
    "build_pxcv",
    "build_wimwv",
    "get_xcvario_polar",
    "load_runtime_config",
]
