"""Runtime configuration contract for the simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_CONTROL_API_PORT = 8181
DEFAULT_XCVARIO_PORT = 4353
DEFAULT_FLARM_PORT = 4354
DEFAULT_SIMULATION_TICK_HZ = 10
DEFAULT_OWNSHIP_HZ = 2
DEFAULT_XCVARIO_GPS_HZ = 1
DEFAULT_TRAFFIC_HZ = 1
DEFAULT_QNH_HPA = 1013.25
DEFAULT_SESSION_ID = "xcvario-sim"
DEFAULT_PRIMARY_DEVICE = "xcvario"
SUPPORTED_PRIMARY_DEVICES = ("xcvario", "sxhawk")


@dataclass(frozen=True)
class HomePosition:
    latitude_deg: float
    longitude_deg: float
    gps_altitude_m: float


@dataclass(frozen=True)
class EndpointConfig:
    bind_host: str = DEFAULT_BIND_HOST
    port: int = DEFAULT_XCVARIO_PORT


@dataclass(frozen=True)
class XcvarioConfig:
    bind_host: str = DEFAULT_BIND_HOST
    port: int = DEFAULT_XCVARIO_PORT
    polar_name: str = ""


@dataclass(frozen=True)
class ControlApiConfig:
    bind_host: str = DEFAULT_BIND_HOST
    port: int = DEFAULT_CONTROL_API_PORT
    cors_allowed_origins: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SchedulerConfig:
    tick_hz: int = DEFAULT_SIMULATION_TICK_HZ
    ownship_hz: int = DEFAULT_OWNSHIP_HZ
    traffic_hz: int = DEFAULT_TRAFFIC_HZ
    gps_hz: int = DEFAULT_XCVARIO_GPS_HZ
    baro_hz: int | None = None

    def __post_init__(self) -> None:
        if self.baro_hz is None:
            object.__setattr__(self, "baro_hz", self.ownship_hz)


@dataclass(frozen=True)
class SimulatorRuntimeConfig:
    session_id: str
    seed: int
    device_qnh_hpa: float
    home_position: HomePosition
    control_api: ControlApiConfig
    xcvario: XcvarioConfig
    flarm: EndpointConfig
    scheduler: SchedulerConfig
    primary_device: str = DEFAULT_PRIMARY_DEVICE


def load_runtime_config(path: Path | str) -> SimulatorRuntimeConfig:
    config_path = Path(path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Simulator runtime config must be a JSON object.")
    return parse_runtime_config(raw)


def parse_runtime_config(raw: Mapping[str, Any]) -> SimulatorRuntimeConfig:
    control_api_raw = _mapping(raw.get("control_api"), key_name="control_api")
    xcvario_raw = _mapping(raw.get("xcvario"), key_name="xcvario")
    flarm_raw = _mapping(raw.get("flarm"), key_name="flarm")
    scheduler_raw = _mapping(raw.get("scheduler"), key_name="scheduler")
    home_raw = _mapping(raw.get("home_position"), key_name="home_position")

    control_api = ControlApiConfig(
        bind_host=_text(control_api_raw.get("bind_host"), default=DEFAULT_BIND_HOST),
        port=_port(control_api_raw.get("port"), default=DEFAULT_CONTROL_API_PORT),
        cors_allowed_origins=tuple(_string_list(control_api_raw.get("cors_allowed_origins", ()))),
    )
    xcvario = EndpointConfig(
        bind_host=_text(xcvario_raw.get("bind_host"), default=DEFAULT_BIND_HOST),
        port=_port(xcvario_raw.get("port"), default=DEFAULT_XCVARIO_PORT),
    )
    xcvario = XcvarioConfig(
        bind_host=xcvario.bind_host,
        port=xcvario.port,
        polar_name=_required_text(xcvario_raw.get("polar_name"), key_name="xcvario.polar_name"),
    )
    flarm = EndpointConfig(
        bind_host=_text(flarm_raw.get("bind_host"), default=DEFAULT_BIND_HOST),
        port=_port(flarm_raw.get("port"), default=DEFAULT_FLARM_PORT),
    )
    baro_hz = _positive_int(
        scheduler_raw.get("baro_hz", scheduler_raw.get("ownship_hz")),
        default=DEFAULT_OWNSHIP_HZ,
    )
    scheduler = SchedulerConfig(
        tick_hz=_positive_int(scheduler_raw.get("tick_hz"), default=DEFAULT_SIMULATION_TICK_HZ),
        ownship_hz=baro_hz,
        traffic_hz=_positive_int(scheduler_raw.get("traffic_hz"), default=DEFAULT_TRAFFIC_HZ),
        gps_hz=_positive_int(scheduler_raw.get("gps_hz"), default=DEFAULT_XCVARIO_GPS_HZ),
        baro_hz=baro_hz,
    )
    home_position = HomePosition(
        latitude_deg=_bounded_float(home_raw.get("latitude_deg"), -90.0, 90.0, key_name="home_position.latitude_deg"),
        longitude_deg=_bounded_float(
            home_raw.get("longitude_deg"),
            -180.0,
            180.0,
            key_name="home_position.longitude_deg",
        ),
        gps_altitude_m=_float_value(home_raw.get("gps_altitude_m"), key_name="home_position.gps_altitude_m"),
    )

    return SimulatorRuntimeConfig(
        session_id=_text(raw.get("session_id"), default=DEFAULT_SESSION_ID),
        seed=_int_value(raw.get("seed"), key_name="seed"),
        device_qnh_hpa=_float_value(raw.get("device_qnh_hpa"), key_name="device_qnh_hpa"),
        primary_device=normalize_primary_device(raw.get("primary_device", raw.get("device_type", DEFAULT_PRIMARY_DEVICE))),
        home_position=home_position,
        control_api=control_api,
        xcvario=xcvario,
        flarm=flarm,
        scheduler=scheduler,
    )


def normalize_primary_device(value: Any) -> str:
    normalized = _text(value, default=DEFAULT_PRIMARY_DEVICE).casefold()
    if normalized not in SUPPORTED_PRIMARY_DEVICES:
        choices = ", ".join(SUPPORTED_PRIMARY_DEVICES)
        raise ValueError(f"primary_device must be one of: {choices}.")
    return normalized


def build_xcsoar_profile_snippet(
    runtime_host: str,
    *,
    primary_device: str = DEFAULT_PRIMARY_DEVICE,
    xcvario_port: int = DEFAULT_XCVARIO_PORT,
    flarm_port: int = DEFAULT_FLARM_PORT,
) -> str:
    host = runtime_host.strip() or "<runtime-host>"
    primary_driver = "LX" if normalize_primary_device(primary_device) == "sxhawk" else "XCVario"
    return "\n".join(
        [
            f'DeviceA="{primary_driver}"',
            'PortType="tcp_client"',
            f'PortIPAddress="{host}"',
            f'PortTCPPort="{_port(xcvario_port, default=DEFAULT_XCVARIO_PORT)}"',
            "",
            'DeviceB="FLARM"',
            'Port2Type="tcp_client"',
            f'Port2IPAddress="{host}"',
            f'Port2TCPPort="{_port(flarm_port, default=DEFAULT_FLARM_PORT)}"',
        ]
    )


def _mapping(value: Any, *, key_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    raise ValueError(f"{key_name} must be an object.")


def _required_text(value: Any, *, key_name: str) -> str:
    text = _text(value, default="")
    if not text:
        raise ValueError(f"{key_name} must be a non-empty string.")
    return text


def _text(value: Any, *, default: str) -> str:
    text = str(value if value is not None else default).strip()
    return text or default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError("cors_allowed_origins must be a list of strings.")


def _port(value: Any, *, default: int) -> int:
    port = _positive_int(value, default=default)
    if port > 65535:
        raise ValueError("Port must be <= 65535.")
    return port


def _positive_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected positive integer, got {value!r}.") from exc
    if number <= 0:
        raise ValueError(f"Expected positive integer, got {value!r}.")
    return number


def _int_value(value: Any, *, key_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key_name} must be an integer.") from exc


def _float_value(value: Any, *, key_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key_name} must be a float.") from exc


def _bounded_float(value: Any, lower: float, upper: float, *, key_name: str) -> float:
    number = _float_value(value, key_name=key_name)
    if number < lower or number > upper:
        raise ValueError(f"{key_name} must be between {lower} and {upper}.")
    return number
