"""FLARM aircraft metadata used by simulated traffic contacts."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import string
from typing import Any, Iterable, Mapping


FLARMNET_DDB_SOURCE_URL = "https://www.flarmnet.org/files/ddb.json"
FLARMNET_DDB_SOURCE_DATE = "2026-06-06"
LAB_TRAFFIC_AIRCRAFT_COUNT = 6
TRAFFIC_DDB_PATH_ENV = "KIGO_FLARM_DDB_PATH"
TRAFFIC_DDB_FILENAMES = (
    "ddb.jason",
    "ddb.json",
    "ogn-ddb.json",
    "ogn.json",
    "ogn_devices.json",
    "flarmnet_ddb.json",
)


@dataclass(frozen=True)
class FlarmTrafficAircraft:
    device_id: str
    competition_id: str
    registration: str
    aircraft_model: str


# Fallback FLARMnet-backed traffic IDs used when no local DDB file is available.
FLARM_TRAFFIC_AIRCRAFT: tuple[FlarmTrafficAircraft, ...] = (
    FlarmTrafficAircraft(device_id="DDA857", competition_id="MF", registration="D-6676", aircraft_model="LS-4"),
    FlarmTrafficAircraft(device_id="DDA85A", competition_id="L1", registration="D-3450", aircraft_model="Discus 2"),
    FlarmTrafficAircraft(device_id="DDA85C", competition_id="TH", registration="D-4449", aircraft_model="Hornet"),
    FlarmTrafficAircraft(device_id="DDA86A", competition_id="1A", registration="D-3358", aircraft_model="LS-4"),
    FlarmTrafficAircraft(device_id="DDA88F", competition_id="", registration="DKERO", aircraft_model="DG-800"),
    FlarmTrafficAircraft(device_id="DDA896", competition_id="TH", registration="D-5799", aircraft_model="ASK-13"),
    FlarmTrafficAircraft(device_id="1804AA", competition_id="27", registration="SP-2585", aircraft_model="Jantar 2B"),
    FlarmTrafficAircraft(device_id="32F759", competition_id="X11", registration="SP-4322", aircraft_model="ASW20FL"),
    FlarmTrafficAircraft(device_id="48D009", competition_id="ZR", registration="SP-4008", aircraft_model="LS-7 WL"),
    FlarmTrafficAircraft(device_id="48D17B", competition_id="RBA", registration="SP-4160", aircraft_model="Glider Astir CS"),
    FlarmTrafficAircraft(device_id="D001A4", competition_id="ZWM", registration="SP-3894", aircraft_model="Jantar Std. 3"),
    FlarmTrafficAircraft(device_id="D00278", competition_id="LK", registration="SP-4157", aircraft_model="Mini Nimbus C"),
    FlarmTrafficAircraft(device_id="D00B06", competition_id="BH", registration="SP-GAVC", aircraft_model="Diana2"),
    FlarmTrafficAircraft(device_id="D00B4D", competition_id="MG", registration="SP-3992", aircraft_model="SZD48-1"),
    FlarmTrafficAircraft(device_id="D01319", competition_id="DS", registration="SP-4193", aircraft_model="DG-300 ELAN WL"),
    FlarmTrafficAircraft(device_id="D0137C", competition_id="HI", registration="SP-3445", aircraft_model="SZD-48-3"),
    FlarmTrafficAircraft(device_id="D017C6", competition_id="HO", registration="SP-3375", aircraft_model="Jantar Standard 3"),
    FlarmTrafficAircraft(device_id="D01C76", competition_id="EP", registration="SP-4052", aircraft_model="Jantar Std. 3"),
    FlarmTrafficAircraft(device_id="D02A21", competition_id="GW", registration="SP-4244", aircraft_model="LS4"),
    FlarmTrafficAircraft(device_id="D02E5F", competition_id="WM", registration="SP-3268", aircraft_model="Glider"),
    FlarmTrafficAircraft(device_id="D02E86", competition_id="I", registration="SP-3440", aircraft_model="Glider"),
    FlarmTrafficAircraft(device_id="D03214", competition_id="O", registration="SP-3314", aircraft_model="Glider"),
    FlarmTrafficAircraft(device_id="D0374E", competition_id="AN", registration="SP-4395", aircraft_model="LS3"),
    FlarmTrafficAircraft(device_id="D4FDEF", competition_id="S95", registration="SP-0095", aircraft_model="HK36 Super Dimona"),
    FlarmTrafficAircraft(device_id="DD0749", competition_id="XD", registration="SP-4415", aircraft_model="ASW15B"),
    FlarmTrafficAircraft(device_id="DD4E87", competition_id="BL", registration="SP-3673", aircraft_model="Jantar Std. 3"),
    FlarmTrafficAircraft(device_id="DD4EE0", competition_id="DC", registration="SP-3712", aircraft_model="LAK 19"),
    FlarmTrafficAircraft(device_id="DD4FF5", competition_id="JAY", registration="SP-3931", aircraft_model="ASW-19"),
    FlarmTrafficAircraft(device_id="DD500B", competition_id="DL", registration="SP-3452", aircraft_model="Jantar Std. 3"),
)

DEFAULT_TRAFFIC_CONTACT_COUNT = len(FLARM_TRAFFIC_AIRCRAFT)


def traffic_aircraft_for(
    seed: int,
    index: int,
    *,
    aircraft: tuple[FlarmTrafficAircraft, ...] | None = None,
) -> FlarmTrafficAircraft:
    if index < 0:
        raise ValueError("index must be >= 0.")
    int(seed)
    resolved_aircraft = aircraft or FLARM_TRAFFIC_AIRCRAFT
    aircraft_index = int(index) % len(resolved_aircraft)
    return resolved_aircraft[aircraft_index]


@lru_cache(maxsize=1)
def load_default_traffic_aircraft() -> tuple[FlarmTrafficAircraft, ...]:
    ddb_path = find_default_traffic_ddb_path()
    if ddb_path is not None:
        aircraft = load_traffic_aircraft_from_ddb(ddb_path)
        if aircraft:
            return aircraft
    return FLARM_TRAFFIC_AIRCRAFT


def find_default_traffic_ddb_path() -> Path | None:
    explicit_path = os.environ.get(TRAFFIC_DDB_PATH_ENV, "").strip()
    if explicit_path:
        path = Path(explicit_path).expanduser()
        if path.is_file():
            return path

    for directory in _default_traffic_ddb_directories():
        for filename in TRAFFIC_DDB_FILENAMES:
            path = directory / filename
            if path.is_file():
                return path
    return None


def load_traffic_aircraft_from_ddb(path: str | Path) -> tuple[FlarmTrafficAircraft, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    aircraft = []
    seen_device_ids: set[str] = set()
    for record in _iter_ddb_record_mappings(raw):
        item = _aircraft_from_ddb_record(record)
        if item is None or item.device_id in seen_device_ids:
            continue
        seen_device_ids.add(item.device_id)
        aircraft.append(item)
    return tuple(aircraft)


def _default_traffic_ddb_directories() -> tuple[Path, ...]:
    cwd = Path.cwd()
    home = Path.home()
    return (
        cwd / "KigoData",
        cwd / "Kigodata",
        cwd.parent / "KigoData",
        cwd.parent / "Kigodata",
        home / "KigoData",
        home / "Kigodata",
        Path("/KigoData"),
        Path("/Kigodata"),
    )


def _iter_ddb_record_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if _text_value(value, ("device_id", "deviceid", "id")):
            yield value
        for child in value.values():
            if isinstance(child, (Mapping, list, tuple)):
                yield from _iter_ddb_record_mappings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_ddb_record_mappings(child)


def _aircraft_from_ddb_record(record: Mapping[str, Any]) -> FlarmTrafficAircraft | None:
    if not _ddb_flag_enabled(record.get("tracked", True)):
        return None
    if not _ddb_flag_enabled(record.get("identified", True)):
        return None

    device_id = _normalize_device_id(_text_value(record, ("device_id", "deviceid", "id")))
    if device_id is None:
        return None

    registration = _text_value(record, ("registration", "aircraft_registration")) or device_id
    competition_id = _text_value(record, ("cn", "competition_number", "competition_id", "callsign"))
    aircraft_model = _text_value(record, ("aircraft_model", "model", "type")) or "Glider"
    return FlarmTrafficAircraft(
        device_id=device_id,
        competition_id=competition_id,
        registration=registration,
        aircraft_model=aircraft_model,
    )


def _text_value(record: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    lower_keys = {str(key).casefold(): key for key in record}
    for key in keys:
        actual_key = lower_keys.get(key.casefold())
        if actual_key is None:
            continue
        value = record.get(actual_key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _normalize_device_id(value: str) -> str | None:
    device_id = value.strip().upper()
    if device_id.startswith("0X"):
        device_id = device_id[2:]
    if len(device_id) != 6:
        return None
    if any(ch not in string.hexdigits.upper() for ch in device_id):
        return None
    return device_id


def _ddb_flag_enabled(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() not in {"0", "n", "no", "false"}
