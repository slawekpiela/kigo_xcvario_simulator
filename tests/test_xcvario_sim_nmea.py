import unittest

from kigo_xcvario_simulator.contracts import OwnshipState, TrafficContact, WindState
from kigo_xcvario_simulator.nmea import (
    build_gpgga,
    build_gprmc,
    build_hchdm,
    build_lxwp0,
    build_lxwp1,
    build_lxwp2,
    build_lxwp3,
    build_pflaa,
    build_pflau,
    build_pov,
    build_pxcv,
    build_wimwv,
    dynamic_pressure_pa_for_speed,
    nmea_checksum,
)
from kigo_xcvario_simulator.state import FlightPhase
from kigo_xcvario_simulator.xcvario_parser import parse_pressure_sentence, read_next_pressure_sample


class _Transport:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read(self, _size: int, _timeout_s: float) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""

    def write(self, _data: bytes, _timeout_s: float) -> None:
        return None

    def close(self) -> None:
        return None


def _ownship() -> OwnshipState:
    return OwnshipState(
        timestamp_utc="2026-05-08T12:00:00.000Z",
        latitude_deg=49.83833,
        longitude_deg=19.00202,
        gps_altitude_m=401.0,
        static_pressure_hpa=965.43,
        device_qnh_hpa=1019.8,
        vertical_speed_ms=2.35,
        speed_kmh=90.0,
        track_deg=84.4,
        on_ground=False,
        phase=FlightPhase.STRAIGHT,
    )


class NmeaBuilderTests(unittest.TestCase):
    def test_pxcv_builder_matches_real_xcvario_layout_and_stays_parser_compatible(self):
        sentence = build_pxcv(_ownship())
        body = "PXCV,2.4,0.00,0,1.000,0,18.0,1019.8,965.4,361.0,,,,,"

        sample = parse_pressure_sentence(sentence)

        self.assertEqual(sentence, f"${body}*{nmea_checksum(body):02X}\r\n")
        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertAlmostEqual(sample.device_qnh_hpa or 0.0, 1019.8, places=2)
        self.assertAlmostEqual(sample.static_pressure_hpa, 965.4, places=2)

    def test_pxcv_builder_marks_circling_as_climb_mode(self):
        ownship = _ownship()
        circling = OwnshipState(
            timestamp_utc=ownship.timestamp_utc,
            latitude_deg=ownship.latitude_deg,
            longitude_deg=ownship.longitude_deg,
            gps_altitude_m=ownship.gps_altitude_m,
            static_pressure_hpa=ownship.static_pressure_hpa,
            device_qnh_hpa=ownship.device_qnh_hpa,
            vertical_speed_ms=ownship.vertical_speed_ms,
            speed_kmh=ownship.speed_kmh,
            track_deg=ownship.track_deg,
            on_ground=ownship.on_ground,
            phase=FlightPhase.CIRCLING_LEFT,
        )

        sentence = build_pxcv(circling)

        self.assertIn(",0,1.000,1,18.0,", sentence)

    def test_pov_builder_matches_openvario_layout_and_remains_parser_compatible(self):
        sentence = build_pov(_ownship())
        body = "POV,P,965.4,Q,361.0,E,2.4,T,18.0"

        sample = parse_pressure_sentence(sentence)

        self.assertEqual(sentence, f"${body}*{nmea_checksum(body):02X}\r\n")
        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertEqual(sample.protocol, "pov")
        self.assertAlmostEqual(sample.static_pressure_hpa, 965.4, places=2)

    def test_dynamic_pressure_builder_uses_static_pressure_temperature_and_speed(self):
        dynamic_pressure_pa = dynamic_pressure_pa_for_speed(
            static_pressure_hpa=965.43,
            speed_kmh=90.0,
            oat_c=18.0,
        )

        self.assertAlmostEqual(dynamic_pressure_pa, 360.99107614714194, places=6)

    def test_wimwv_builder_matches_xcvario_true_wind_output(self):
        sentence = build_wimwv(WindState(direction_deg=270.0, speed_kmh=25.5))
        body = "WIMWV,270.0,T,25.5,K,A"

        self.assertEqual(sentence, f"${body}*{nmea_checksum(body):02X}\r\n")

    def test_hchdm_builder_provides_heading_for_heading_up_consumers(self):
        sentence = build_hchdm(_ownship())
        body = "HCHDM,84.4,M"

        self.assertEqual(sentence, f"${body}*{nmea_checksum(body):02X}\r\n")

    def test_lxwp0_builder_matches_sxhawk_lx_parser_layout(self):
        sentence = build_lxwp0(_ownship(), WindState(direction_deg=270.0, speed_kmh=25.5))
        body = "LXWP0,Y,90.0,401.0,2.35,2.35,2.35,2.35,2.35,2.35,84.4,270.0,25.5"

        self.assertEqual(sentence, f"${body}*{nmea_checksum(body):02X}\r\n")

    def test_lxwp0_builder_uses_device_altitude_when_available(self):
        ownship = _ownship()
        ownship = OwnshipState(
            timestamp_utc=ownship.timestamp_utc,
            latitude_deg=ownship.latitude_deg,
            longitude_deg=ownship.longitude_deg,
            gps_altitude_m=ownship.gps_altitude_m,
            static_pressure_hpa=ownship.static_pressure_hpa,
            device_qnh_hpa=ownship.device_qnh_hpa,
            vertical_speed_ms=ownship.vertical_speed_ms,
            speed_kmh=ownship.speed_kmh,
            track_deg=ownship.track_deg,
            on_ground=ownship.on_ground,
            phase=ownship.phase,
            device_altitude_m=455.4,
        )

        sentence = build_lxwp0(ownship, WindState(direction_deg=270.0, speed_kmh=25.5))

        self.assertIn("$LXWP0,Y,90.0,455.4,2.35", sentence)

    def test_lxwp1_lxwp2_and_lxwp3_builders_cover_sxhawk_metadata_settings_and_qnh(self):
        lxwp1_body = "LXWP1,SxHAWK,SXSIM0001,I9.56/S9.54,SIM,"
        lxwp2_body = "LXWP2,1.5,1.20,7,,,,65"
        lxwp3_body = "LXWP3,0.00,,,,,,,,,,,,"

        self.assertEqual(build_lxwp1(), f"${lxwp1_body}*{nmea_checksum(lxwp1_body):02X}\r\n")
        self.assertEqual(
            build_lxwp2(
                mac_cready_ms=1.5,
                ballast_overload_factor=1.2,
                bugs_degradation_percent=7,
                volume_percent=65,
            ),
            f"${lxwp2_body}*{nmea_checksum(lxwp2_body):02X}\r\n",
        )
        self.assertEqual(build_lxwp3(qnh_hpa=1013.25), f"${lxwp3_body}*{nmea_checksum(lxwp3_body):02X}\r\n")

    def test_gps_builders_work_with_existing_stream_reader(self):
        stream = (
            build_gprmc(_ownship())
            + build_gpgga(_ownship())
            + build_pov(_ownship())
        ).encode("ascii")

        sample, remainder = read_next_pressure_sample(_Transport([stream]), timeout_s=0.2)

        self.assertEqual(remainder, b"")
        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertAlmostEqual(sample.latitude_deg or 0.0, 49.83833, places=4)
        self.assertAlmostEqual(sample.longitude_deg or 0.0, 19.00202, places=4)

    def test_checksum_builder_matches_expected_xor(self):
        self.assertEqual(
            nmea_checksum("GPRMC,123519.00,A,4807.038,N,01131.000,E,022.4,084.4,230394,,,A"),
            0x52,
        )

    def test_flarm_builders_emit_expected_prefixes_and_checksum(self):
        traffic = (
            TrafficContact(
                contact_id="TFC-01",
                relative_north_m=123.0,
                relative_east_m=-45.0,
                relative_altitude_m=67.0,
                track_deg=90.0,
                climb_ms=1.5,
                alarm_level=1,
                aircraft_id="A1B2C3",
            ),
        )

        pflau = build_pflau(traffic)
        pflaa = build_pflaa(traffic[0])

        self.assertTrue(pflau.startswith("$PFLAU,1,1,2,1,1,"))
        self.assertIn("A1B2C3", pflau)
        self.assertTrue(pflaa.startswith("$PFLAA,1,123,-45,67,2,A1B2C3,90,0,0,1.5,1*"))
        self.assertTrue(pflau.endswith("\r\n"))
        self.assertTrue(pflaa.endswith("\r\n"))


if __name__ == "__main__":
    unittest.main()
