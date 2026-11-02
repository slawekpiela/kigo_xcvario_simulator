"""Bounded IGC B-record parser and interpolated ownship track."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import math
import re

from .flight_math import EARTH_RADIUS_M, normalize_heading_deg

MAX_IGC_BYTES = 3_000_000
MAX_FIXES = 40_000
FIX = re.compile(r"^B(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{3})([NS])(\d{3})(\d{2})(\d{3})([EW])([AV])(\d{5})(\d{5})")


@dataclass(frozen=True)
class Fix:
    elapsed_s: int
    latitude_deg: float
    longitude_deg: float
    altitude_m: float


@dataclass(frozen=True)
class ReplaySample:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    speed_kmh: float
    track_deg: float
    climb_ms: float


class ReplayTrack:
    def __init__(self, fixes: tuple[Fix, ...]):
        self.fixes = fixes
        self.times = tuple(fix.elapsed_s for fix in fixes)
        self.duration_s = self.times[-1]

    def sample(self, elapsed_s: float) -> ReplaySample:
        elapsed_s = min(max(0.0, elapsed_s), self.duration_s)
        index = min(bisect_right(self.times, elapsed_s), len(self.fixes) - 1)
        before, after = self.fixes[index - 1], self.fixes[index]
        duration = after.elapsed_s - before.elapsed_s
        ratio = (elapsed_s - before.elapsed_s) / duration
        lat1, lat2 = math.radians(before.latitude_deg), math.radians(after.latitude_deg)
        dlon = math.radians(after.longitude_deg - before.longitude_deg)
        north = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        east = math.sin(dlon) * math.cos(lat2)
        bearing = normalize_heading_deg(math.degrees(math.atan2(east, north)))
        central_angle = math.atan2(math.hypot(north, east), math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(dlon))
        longitude_delta = (after.longitude_deg - before.longitude_deg + 180) % 360 - 180
        return ReplaySample(
            latitude_deg=before.latitude_deg + (after.latitude_deg - before.latitude_deg) * ratio,
            longitude_deg=(before.longitude_deg + longitude_delta * ratio + 180) % 360 - 180,
            altitude_m=before.altitude_m + (after.altitude_m - before.altitude_m) * ratio,
            speed_kmh=EARTH_RADIUS_M * central_angle / duration * 3.6,
            track_deg=bearing,
            climb_ms=(after.altitude_m - before.altitude_m) / duration,
        )


def parse_igc(data: bytes) -> ReplayTrack:
    if len(data) > MAX_IGC_BYTES:
        raise ValueError("IGC file is too large (maximum 3 MB).")
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("IGC file must contain ASCII records.") from exc
    fixes = []
    day_offset = 0
    previous_time = None
    start_time = None
    for line in lines:
        match = FIX.match(line)
        if not match or match[12] != "A":
            continue
        hour, minute, second = map(int, match.group(1, 2, 3))
        lat_deg, lat_min, lat_frac = map(int, match.group(4, 5, 6))
        lon_deg, lon_min, lon_frac = map(int, match.group(8, 9, 10))
        if hour > 23 or minute > 59 or second > 59 or lat_deg > 90 or lon_deg > 180 or lat_min > 59 or lon_min > 59:
            raise ValueError("IGC contains an invalid fix.")
        second_of_day = hour * 3600 + minute * 60 + second
        if previous_time is not None and second_of_day < previous_time:
            if previous_time - second_of_day < 12 * 3600:
                raise ValueError("IGC fix times are out of order.")
            day_offset += 86400
        previous_time = second_of_day
        absolute_time = second_of_day + day_offset
        if start_time is None:
            start_time = absolute_time
        elapsed = absolute_time - start_time
        if fixes and elapsed == fixes[-1].elapsed_s:
            continue
        latitude = lat_deg + (lat_min + lat_frac / 1000) / 60
        longitude = lon_deg + (lon_min + lon_frac / 1000) / 60
        if match[7] == "S":
            latitude = -latitude
        if match[11] == "W":
            longitude = -longitude
        fixes.append(Fix(elapsed, latitude, longitude, float(int(match[14]))))
        if len(fixes) > MAX_FIXES:
            raise ValueError("IGC has too many fixes (maximum 40,000).")
    if len(fixes) < 2:
        raise ValueError("IGC needs at least two valid fixes at different times.")
    return ReplayTrack(tuple(fixes))
