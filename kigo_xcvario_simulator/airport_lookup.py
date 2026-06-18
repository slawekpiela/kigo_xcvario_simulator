"""Local start-location lookup backed by cached OpenAIP data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
from typing import Iterable, Mapping
import unicodedata


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
    "KMEV": AirportPosition(
        icao="KMEV",
        name="Minden Tahoe Airport",
        latitude_deg=39.0003,
        longitude_deg=-119.751,
        gps_altitude_m=1439.0,
    ),
}

_KNOWN_LOCATION_ICAO_ALIASES = {
    "minden tahoe": "KMEV",
    "minden tahoe airport": "KMEV",
    "minden us": "KMEV",
    "minden usa": "KMEV",
    "minden united states": "KMEV",
    "minden united states of america": "KMEV",
    "minden nevada": "KMEV",
    "minden nv": "KMEV",
    "minden nevada us": "KMEV",
    "minden nevada usa": "KMEV",
    "worcester south africa": "FWCT",
    "worcester za": "FWCT",
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

    def find(self, raw_query: object) -> AirportPosition:
        query = str(raw_query or "").strip()
        if _looks_like_icao(query):
            return self.find_by_icao(query)
        return self.find_by_place_country(query)

    def find_by_icao(self, raw_icao: object) -> AirportPosition:
        icao = _normalize_icao(raw_icao)
        cache = self._read_cache()
        cached = cache.get(icao)
        if isinstance(cached, Mapping):
            return _airport_from_mapping(icao, cached)

        try:
            airport = self._search_data_dirs(icao)
        except ValueError:
            known = _KNOWN_AIRPORT_POSITIONS.get(icao)
            if known is not None:
                return known
            raise
        cache[icao] = asdict(airport)
        self._write_cache(cache)
        return airport

    def find_by_place_country(self, raw_query: object) -> AirportPosition:
        query = str(raw_query or "").strip()
        normalized_query = _normalize_search_text(query)
        if not normalized_query:
            raise ValueError("start location must be an ICAO code or place and country.")

        cache_key = f"location:{normalized_query}"
        cache = self._read_cache()
        cached = cache.get(cache_key)
        if isinstance(cached, Mapping):
            return _airport_from_mapping(cache_key, cached)

        alias_icao = _KNOWN_LOCATION_ICAO_ALIASES.get(normalized_query)
        if alias_icao is not None:
            airport = self.find_by_icao(alias_icao)
            cache[cache_key] = asdict(airport)
            self._write_cache(cache)
            return airport

        place, country_code = _split_place_country(normalized_query)
        airport = self._search_place_data_dirs(place, country_code, query)
        cache[cache_key] = asdict(airport)
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

    def _search_place_data_dirs(self, place: str, country_code: str, raw_query: str) -> AirportPosition:
        best: tuple[int, AirportPosition] | None = None
        for data_dir in self._data_dirs:
            if not data_dir.is_dir():
                continue
            for json_path in _candidate_place_files(data_dir, country_code):
                for score, airport in _find_place_matches_in_file(json_path, place, country_code):
                    if best is None or score > best[0]:
                        best = (score, airport)
        if best is not None:
            return best[1]
        searched = ", ".join(str(path) for path in self._data_dirs)
        raise ValueError(f"start location {raw_query!r} not found in local OpenAIP data: {searched}")

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


def _candidate_place_files(data_dir: Path, country_code: str) -> tuple[Path, ...]:
    preferred = data_dir / f"{country_code.lower()}_apt.json"
    if preferred.is_file():
        return (preferred,)
    return tuple(sorted(data_dir.glob("*_apt.json")))


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


def _find_place_matches_in_file(json_path: Path, place: str, country_code: str) -> list[tuple[int, AirportPosition]]:
    try:
        records = json.loads(json_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    if not isinstance(records, list):
        return []
    matches: list[tuple[int, AirportPosition]] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        if str(record.get("country", "")).strip().upper() != country_code:
            continue
        score = _score_place_record(record, place)
        if score <= 0:
            continue
        identifier = str(record.get("icaoCode") or record.get("altIdentifier") or place).strip().upper()
        matches.append((score, _airport_from_openaip_record(identifier, record)))
    return matches


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
        icao=str(value.get("icao") or icao).strip().upper(),
        name=str(value.get("name") or icao),
        latitude_deg=float(value["latitude_deg"]),
        longitude_deg=float(value["longitude_deg"]),
        gps_altitude_m=float(value["gps_altitude_m"]),
    )


def _looks_like_icao(raw_query: str) -> bool:
    query = str(raw_query or "").strip()
    return len(query) == 4 and query.isalnum()


def _normalize_icao(raw_icao: object) -> str:
    icao = str(raw_icao or "").strip().upper()
    if len(icao) != 4 or not icao.isalnum():
        raise ValueError("airport ICAO must be a four-character code.")
    return icao


def _normalize_search_text(raw_value: object) -> str:
    text = unicodedata.normalize("NFKD", str(raw_value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(text.split())


def _split_place_country(normalized_query: str) -> tuple[str, str]:
    for country_name, country_code in sorted(_COUNTRY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        suffix = f" {country_name}"
        if normalized_query.endswith(suffix):
            place = normalized_query[: -len(suffix)].strip()
            if place:
                return place, country_code
    tokens = normalized_query.split()
    if len(tokens) >= 2 and len(tokens[-1]) == 2 and tokens[-1].isalpha():
        return " ".join(tokens[:-1]), tokens[-1].upper()
    raise ValueError("start location must be an ICAO code or place and country, e.g. 'KMEV' or 'Minden USA'.")


def _score_place_record(record: Mapping[str, object], place: str) -> int:
    name = _normalize_search_text(record.get("name"))
    if not name:
        return 0
    place_tokens = place.split()
    name_tokens = set(name.split())
    if name == place:
        score = 100
    elif name.startswith(f"{place} "):
        score = 90
    elif place in name:
        score = 80
    elif all(token in name_tokens for token in place_tokens):
        score = 60
    else:
        return 0
    if record.get("icaoCode"):
        score += 10
    if record.get("private") is True:
        score -= 5
    if record.get("type") == 7:
        score -= 20
    return score


_COUNTRY_ALIASES = {
    "au": "AU",
    "australia": "AU",
    "ca": "CA",
    "canada": "CA",
    "de": "DE",
    "germany": "DE",
    "niemcy": "DE",
    "fr": "FR",
    "france": "FR",
    "gb": "GB",
    "great britain": "GB",
    "uk": "GB",
    "united kingdom": "GB",
    "nz": "NZ",
    "new zealand": "NZ",
    "pl": "PL",
    "poland": "PL",
    "polska": "PL",
    "us": "US",
    "usa": "US",
    "united states": "US",
    "united states of america": "US",
    "za": "ZA",
    "south africa": "ZA",
}


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
