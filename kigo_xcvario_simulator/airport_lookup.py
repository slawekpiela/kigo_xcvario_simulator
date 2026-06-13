"""Local ICAO airport lookup backed by cached OpenAIP data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Iterable, Mapping


DEFAULT_CACHE_PATH = Path(".cache") / "airport_icao_cache.json"


@dataclass(frozen=True)
class AirportPosition:
    icao: str
    name: str
    latitude_deg: float
    longitude_deg: float
    gps_altitude_m: float


_KNOWN_AIRPORT_POSITIONS = {
    "FWCT": AirportPosition(
        icao="FWCT",
        name="Worcester",
        latitude_deg=-33.663,
        longitude_deg=19.415,
        gps_altitude_m=205.0,
    ),
}


class AirportLookup:
    def __init__(
        self,
        *,
        data_dirs: Iterable[Path | str] | None = None,
        cache_path: Path | str | None = None,
    ) -> None:
        self._data_dirs = tuple(Path(path) for path in data_dirs) if data_dirs is not None else _default_data_dirs()
        self._cache_path = Path(os.environ.get("KIGO_AIRPORT_CACHE_PATH", cache_path or DEFAULT_CACHE_PATH))

    def find_by_icao(self, raw_icao: object) -> AirportPosition:
        icao = _normalize_icao(raw_icao)
        cache = self._read_cache()
        cached = cache.get(icao)
        if isinstance(cached, Mapping):
            return _airport_from_mapping(icao, cached)

        known = _KNOWN_AIRPORT_POSITIONS.get(icao)
        if known is not None:
            return known

        airport = self._search_data_dirs(icao)
        cache[icao] = asdict(airport)
        self._write_cache(cache)
        return airport

    def _search_data_dirs(self, icao: str) -> AirportPosition:
        for data_dir in self._data_dirs:
            if not data_dir.is_dir():
                continue
            for json_path in _candidate_files(data_dir, icao):
                airport = _find_in_file(json_path, icao)
                if airport is not None:
                    return airport
        searched = ", ".join(str(path) for path in self._data_dirs)
        raise ValueError(f"airport ICAO {icao!r} not found in local OpenAIP data: {searched}")

    def _read_cache(self) -> dict[str, object]:
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write_cache(self, cache: Mapping[str, object]) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _default_data_dirs() -> tuple[Path, ...]:
    env_dir = os.environ.get("KIGO_AIRPORT_DATA_DIR")
    candidates: list[Path] = []
    if env_dir:
        candidates.append(Path(env_dir))

    cwd = Path.cwd()
    for base in (cwd, *cwd.parents):
        candidates.append(base / "appdata" / "openaip")
        candidates.append(base / "Kigo" / "appdata" / "openaip")

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return tuple(unique)


def _candidate_files(data_dir: Path, icao: str) -> tuple[Path, ...]:
    likely_country = _ICAO_PREFIX_TO_OPENAIP_COUNTRY.get(icao[0])
    preferred = data_dir / f"{likely_country}_apt.json" if likely_country else None
    files = sorted(data_dir.glob("*_apt.json"))
    if preferred is None or preferred not in files:
        return tuple(files)
    return (preferred, *(path for path in files if path != preferred))


def _find_in_file(json_path: Path, icao: str) -> AirportPosition | None:
    try:
        records = json.loads(json_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(records, list):
        return None
    for record in records:
        if not isinstance(record, Mapping):
            continue
        if str(record.get("icaoCode", "")).strip().upper() != icao:
            continue
        return _airport_from_openaip_record(icao, record)
    return None


def _airport_from_openaip_record(icao: str, record: Mapping[str, object]) -> AirportPosition:
    geometry = record.get("geometry")
    if not isinstance(geometry, Mapping):
        raise ValueError(f"airport ICAO {icao!r} has no geometry")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError(f"airport ICAO {icao!r} has invalid coordinates")

    elevation = record.get("elevation")
    elevation_m = 0.0
    if isinstance(elevation, Mapping) and elevation.get("value") is not None:
        elevation_m = float(elevation["value"])

    return AirportPosition(
        icao=icao,
        name=str(record.get("name") or icao),
        latitude_deg=float(coordinates[1]),
        longitude_deg=float(coordinates[0]),
        gps_altitude_m=elevation_m,
    )


def _airport_from_mapping(icao: str, value: Mapping[str, object]) -> AirportPosition:
    return AirportPosition(
        icao=icao,
        name=str(value.get("name") or icao),
        latitude_deg=float(value["latitude_deg"]),
        longitude_deg=float(value["longitude_deg"]),
        gps_altitude_m=float(value["gps_altitude_m"]),
    )


def _normalize_icao(raw_icao: object) -> str:
    icao = str(raw_icao or "").strip().upper()
    if len(icao) != 4 or not icao.isalnum():
        raise ValueError("airport ICAO must be a four-character code.")
    return icao


_ICAO_PREFIX_TO_OPENAIP_COUNTRY = {
    "K": "us",
    "C": "ca",
    "E": "de",
    "L": "fr",
    "Y": "au",
    "Z": "cn",
    "N": "nz",
    "F": "za",
}
