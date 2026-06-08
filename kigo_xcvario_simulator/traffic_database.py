"""Configured FLARM aircraft used by simulated traffic contacts."""

from __future__ import annotations

from dataclasses import dataclass


FLARMNET_DDB_SOURCE_URL = "https://www.flarmnet.org/files/ddb.json"
FLARMNET_DDB_SOURCE_DATE = "2026-06-06"
LAB_TRAFFIC_AIRCRAFT_COUNT = 6


@dataclass(frozen=True)
class FlarmTrafficAircraft:
    device_id: str
    competition_id: str
    registration: str
    aircraft_model: str


# FLARMnet-backed traffic IDs requested for the FLARM stream.
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


def traffic_aircraft_for(seed: int, index: int) -> FlarmTrafficAircraft:
    if index < 0:
        raise ValueError("index must be >= 0.")
    int(seed)
    aircraft_index = int(index) % len(FLARM_TRAFFIC_AIRCRAFT)
    return FLARM_TRAFFIC_AIRCRAFT[aircraft_index]
