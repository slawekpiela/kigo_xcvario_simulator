"""Start-location lookup backed by local airport data and online geocoding."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
from typing import Callable, Iterable, Mapping
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_CACHE_PATH = Path(".cache") / "airport_icao_cache.json"
DEFAULT_GEOCODER_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_GEOCODER_USER_AGENT = (
    "kigo-xcvario-simulator/1.0 "
    "(https://github.com/slawekpiela/kigo_xcvario_simulator)"
)
DEFAULT_GEOCODER_TIMEOUT_S = 5.0


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


class AirportLookup:
    def __init__(
        self,
        *,
        data_dirs: Iterable[Path | str] | None = None,
        cache_path: Path | str | None = None,
        geocoder_search_url: str | None = None,
        geocoder_timeout_s: float = DEFAULT_GEOCODER_TIMEOUT_S,
        urlopen_func: Callable[..., object] | None = None,
    ) -> None:
        self._data_dirs = tuple(Path(path) for path in data_dirs) if data_dirs is not None else _default_data_dirs()
        self._cache_path = Path(os.environ.get("KIGO_AIRPORT_CACHE_PATH", cache_path or DEFAULT_CACHE_PATH))
        self._geocoder_search_url = os.environ.get(
            "KIGO_GEOCODER_SEARCH_URL",
            geocoder_search_url or DEFAULT_GEOCODER_SEARCH_URL,
        )
        self._geocoder_timeout_s = float(os.environ.get("KIGO_GEOCODER_TIMEOUT_S", geocoder_timeout_s))
        self._urlopen = urlopen_func or urlopen

    def find(self, raw_query: object) -> AirportPosition:
        query = str(raw_query or "").strip()
        if _looks_like_icao(query):
            return self.find_by_icao(query)
        return self.find_by_free_text_location(query)

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

    def find_by_free_text_location(self, raw_query: object) -> AirportPosition:
        query = str(raw_query or "").strip()
        normalized_query = _normalize_search_text(query)
        if not normalized_query:
            raise ValueError("start location must be an ICAO code or free-text place query.")

        cache_key = f"geocode:{normalized_query}"
        cache = self._read_cache()
        cached = cache.get(cache_key)
        if isinstance(cached, Mapping):
            return _airport_from_mapping(cache_key, cached)

        airport = self._geocode_free_text_location(query, normalized_query)
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

    def _geocode_free_text_location(self, query: str, normalized_query: str) -> AirportPosition:
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": "1",
            "addressdetails": "1",
        }
        country_code = _country_code_from_query(normalized_query)
        if country_code is not None:
            params["countrycodes"] = country_code.lower()
        url = f"{self._geocoder_search_url}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Accept-Language": "en",
                "User-Agent": os.environ.get("KIGO_GEOCODER_USER_AGENT", DEFAULT_GEOCODER_USER_AGENT),
            },
        )
        try:
            with self._urlopen(request, timeout=self._geocoder_timeout_s) as response:
                records = json.load(response)
        except HTTPError as exc:
            raise ValueError(f"internet geocoding failed for {query!r}: HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ValueError(f"internet geocoding failed for {query!r}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"internet geocoding failed for {query!r}: invalid JSON response") from exc

        if not isinstance(records, list) or not records:
            raise ValueError(f"internet geocoding found no result for {query!r}")
        record = records[0]
        if not isinstance(record, Mapping):
            raise ValueError(f"internet geocoding returned an invalid result for {query!r}")
        try:
            latitude_deg = float(record["lat"])
            longitude_deg = float(record["lon"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"internet geocoding returned invalid coordinates for {query!r}") from exc
        return AirportPosition(
            icao="GEOCODE",
            name=str(record.get("display_name") or record.get("name") or query),
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            gps_altitude_m=0.0,
        )

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


def _country_code_from_query(normalized_query: str) -> str | None:
    for country_name, country_code in sorted(_COUNTRY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if normalized_query == country_name or normalized_query.endswith(f" {country_name}"):
            return country_code
    return None


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
