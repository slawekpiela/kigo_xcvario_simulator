"""Curated FLARMnet DDB aircraft used by simulated traffic contacts."""

from __future__ import annotations

from dataclasses import dataclass

FLARMNET_DDB_SOURCE_URL = "https://www.flarmnet.org/files/ddb.json"
FLARMNET_DDB_SOURCE_DATE = "2026-06-06"


@dataclass(frozen=True)
class FlarmTrafficAircraft:
    device_id: str
    competition_id: str
    registration: str
    aircraft_model: str


# Downloaded from FLARMnet DDB on 2026-06-06 and filtered to identified,
# tracked FLARM records with Polish registrations and non-empty competition IDs.
FLARM_TRAFFIC_AIRCRAFT: tuple[FlarmTrafficAircraft, ...] = (
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
    FlarmTrafficAircraft(device_id="DD501F", competition_id="V4", registration="SP-4262", aircraft_model="LS-4"),
    FlarmTrafficAircraft(device_id="DD5026", competition_id="T3", registration="SP-4125", aircraft_model="Grob G103C Twin III Acro"),
    FlarmTrafficAircraft(device_id="DD502E", competition_id="YZ", registration="SP-3648", aircraft_model="SZD-48-3 Jantar Std 3"),
    FlarmTrafficAircraft(device_id="DD502F", competition_id="SZ2", registration="SP-4055", aircraft_model="Grob Twin II Acro"),
    FlarmTrafficAircraft(device_id="DD503C", competition_id="CU", registration="SP-3705", aircraft_model="PW-5"),
    FlarmTrafficAircraft(device_id="DD5072", competition_id="VY", registration="SP-3453", aircraft_model="Jantar Std. 3"),
    FlarmTrafficAircraft(device_id="DD5189", competition_id="E7", registration="SP-4174", aircraft_model="LS4"),
    FlarmTrafficAircraft(device_id="DD5274", competition_id="IP", registration="SP-4065", aircraft_model="Pegase 101 AP"),
    FlarmTrafficAircraft(device_id="DD8396", competition_id="BG", registration="SP-4455", aircraft_model="Astir Club IIIB"),
    FlarmTrafficAircraft(device_id="DD8502", competition_id="MK", registration="SP-4053", aircraft_model="Jantar Std. 3"),
    FlarmTrafficAircraft(device_id="DD8A7F", competition_id="PC", registration="SP-4288", aircraft_model="LS 3"),
    FlarmTrafficAircraft(device_id="DD8AA7", competition_id="L70", registration="SP-4353", aircraft_model="LS1-f"),
    FlarmTrafficAircraft(device_id="DD8E54", competition_id="KB", registration="SP-4420", aircraft_model="DG-100"),
    FlarmTrafficAircraft(device_id="DD9397", competition_id="KZ", registration="SP-4051", aircraft_model="DG-100"),
    FlarmTrafficAircraft(device_id="DD95DB", competition_id="29", registration="SP-4131", aircraft_model="Ventus"),
    FlarmTrafficAircraft(device_id="DD9A9F", competition_id="4C", registration="SP-4428", aircraft_model="LS4"),
    FlarmTrafficAircraft(device_id="DD9B49", competition_id="YM", registration="SP-4121", aircraft_model="Ventus"),
    FlarmTrafficAircraft(device_id="DD9C4E", competition_id="RX", registration="SP-4152", aircraft_model="Mini Nimbus"),
    FlarmTrafficAircraft(device_id="DD9C66", competition_id="7W", registration="SP-4149", aircraft_model="LS1f neo"),
    FlarmTrafficAircraft(device_id="DD9EF8", competition_id="PZ", registration="SP-4044", aircraft_model="Jantar Std. 3"),
    FlarmTrafficAircraft(device_id="DDA48F", competition_id="SZ", registration="SP-4016", aircraft_model="Glider"),
    FlarmTrafficAircraft(device_id="DDA4FC", competition_id="SB", registration="SP-4042", aircraft_model="Jantar Std. 3"),
    FlarmTrafficAircraft(device_id="DDA756", competition_id="AKM", registration="SP-4113", aircraft_model="DG101G"),
    FlarmTrafficAircraft(device_id="DDAB2A", competition_id="RH", registration="SP-4493", aircraft_model="DG-300"),
    FlarmTrafficAircraft(device_id="DDAB39", competition_id="DG", registration="SP-3825", aircraft_model="DG-100"),
    FlarmTrafficAircraft(device_id="DDACDA", competition_id="MG", registration="SP-3709", aircraft_model="Jantar Std."),
    FlarmTrafficAircraft(device_id="DDAD01", competition_id="AS", registration="SP-3817", aircraft_model="Jantar Std 3"),
    FlarmTrafficAircraft(device_id="DDB1DF", competition_id="TM", registration="SP-4787", aircraft_model="Discus B"),
    FlarmTrafficAircraft(device_id="DDB1EE", competition_id="IP", registration="SP-3843", aircraft_model="DG-100G Elan"),
    FlarmTrafficAircraft(device_id="DDB28E", competition_id="Y11", registration="SP-4430", aircraft_model="DG300"),
    FlarmTrafficAircraft(device_id="DDBCF4", competition_id="44", registration="SP-4144", aircraft_model="G102 Club Astir II"),
    FlarmTrafficAircraft(device_id="DDC00F", competition_id="FT", registration="SP-3777", aircraft_model="ASW-15"),
    FlarmTrafficAircraft(device_id="DDC1E0", competition_id="PB", registration="SP-3921", aircraft_model="Jantar Std.3"),
    FlarmTrafficAircraft(device_id="DDC33A", competition_id="AK", registration="SP-3866", aircraft_model="GLIDER"),
    FlarmTrafficAircraft(device_id="DDD244", competition_id="AN", registration="SP-4395", aircraft_model="LS3"),
    FlarmTrafficAircraft(device_id="DDD360", competition_id="1W", registration="SP-4109", aircraft_model="DG 101G"),
    FlarmTrafficAircraft(device_id="DDD428", competition_id="AA", registration="SP-3292", aircraft_model="Jantar Std. 3"),
    FlarmTrafficAircraft(device_id="DDD98E", competition_id="TS", registration="SP-4219", aircraft_model="ASW-19"),
    FlarmTrafficAircraft(device_id="DDDA11", competition_id="DK", registration="SP-4515", aircraft_model="Discus bT"),
    FlarmTrafficAircraft(device_id="DDDADC", competition_id="U9", registration="SP-4067", aircraft_model="Grob Astir CS-77"),
    FlarmTrafficAircraft(device_id="DDDBE8", competition_id="CT", registration="SP-4200", aircraft_model="DG300"),
    FlarmTrafficAircraft(device_id="DDDC2B", competition_id="88", registration="SP-3988", aircraft_model="Mosquito"),
    FlarmTrafficAircraft(device_id="DDDE65", competition_id="WR", registration="SP-3877", aircraft_model="SZD 48-3 Jantar Std3"),
    FlarmTrafficAircraft(device_id="DDDEDD", competition_id="CB", registration="SP-4300", aircraft_model="Glider"),
    FlarmTrafficAircraft(device_id="DDDF59", competition_id="B", registration="SP-4222", aircraft_model="Janus B"),
    FlarmTrafficAircraft(device_id="DDDFA2", competition_id="MA", registration="SP-3963", aircraft_model="DG-300"),
    FlarmTrafficAircraft(device_id="DDE1DC", competition_id="X56", registration="SP-4192", aircraft_model="ASW 20 F"),
    FlarmTrafficAircraft(device_id="DDE2B0", competition_id="BK", registration="SP-3687", aircraft_model="Jantar Std. 3"),
    FlarmTrafficAircraft(device_id="DDE2D0", competition_id="M", registration="SP-2626", aircraft_model="SZD-32A FOKA 5"),
    FlarmTrafficAircraft(device_id="DDE357", competition_id="TO", registration="SP-4024", aircraft_model="SZD-41A Jantar"),
    FlarmTrafficAircraft(device_id="DDE489", competition_id="25", registration="SP-2586", aircraft_model="glider"),
    FlarmTrafficAircraft(device_id="DDEA6C", competition_id="5K", registration="SP-4096", aircraft_model="Glider"),
    FlarmTrafficAircraft(device_id="DDEF66", competition_id="TK", registration="SP-3693", aircraft_model="SZD-55"),
    FlarmTrafficAircraft(device_id="DDEFFE", competition_id="DG", registration="SP-3925", aircraft_model="DG-300"),
    FlarmTrafficAircraft(device_id="DDF0FB", competition_id="PM", registration="SP-3975", aircraft_model="ASH-26 E"),
    FlarmTrafficAircraft(device_id="DDFD47", competition_id="SZD", registration="SP-8013", aircraft_model="SZD-54"),
    FlarmTrafficAircraft(device_id="DDFDFD", competition_id="FLY", registration="SP-4249", aircraft_model="Mini Nimbus HS7"),
    FlarmTrafficAircraft(device_id="DF03E9", competition_id="TO", registration="SP-4134", aircraft_model="Centrair 101A Pegase"),
    FlarmTrafficAircraft(device_id="DF08C5", competition_id="ES", registration="SP-4048", aircraft_model="glider"),
)


def traffic_aircraft_for(seed: int, index: int) -> FlarmTrafficAircraft:
    if index < 0:
        raise ValueError("index must be >= 0.")
    aircraft_index = (int(seed) * 17 + int(index)) % len(FLARM_TRAFFIC_AIRCRAFT)
    return FLARM_TRAFFIC_AIRCRAFT[aircraft_index]
