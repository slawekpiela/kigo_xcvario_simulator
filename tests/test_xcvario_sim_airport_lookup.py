import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kigo_xcvario_simulator.airport_lookup import AirportLookup


class AirportLookupTests(unittest.TestCase):
    def test_known_fwct_worcester_position_is_available_without_openaip_data(self):
        with TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "airport-cache.json"
            lookup = AirportLookup(data_dirs=(Path(temp_dir) / "missing",), cache_path=cache_path)

            airport = lookup.find_by_icao("fwct")

            self.assertEqual(airport.icao, "FWCT")
            self.assertEqual(airport.name, "Worcester")
            self.assertAlmostEqual(airport.latitude_deg, -33.663, places=6)
            self.assertAlmostEqual(airport.longitude_deg, 19.415, places=6)
            self.assertAlmostEqual(airport.gps_altitude_m, 205.0, places=6)

    def test_known_minden_tahoe_location_alias_is_available_without_openaip_data(self):
        with TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "airport-cache.json"
            lookup = AirportLookup(data_dirs=(Path(temp_dir) / "missing",), cache_path=cache_path)

            for query in ("Minden Tahoe", "Minden USA"):
                with self.subTest(query=query):
                    airport = lookup.find(query)

                    self.assertEqual(airport.icao, "KMEV")
                    self.assertEqual(airport.name, "Minden Tahoe Airport")
                    self.assertAlmostEqual(airport.latitude_deg, 39.0003, places=6)
                    self.assertAlmostEqual(airport.longitude_deg, -119.751, places=6)
                    self.assertAlmostEqual(airport.gps_altitude_m, 1439.0, places=6)

    def test_lookup_caches_airport_position_after_first_file_search(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "openaip"
            data_dir.mkdir()
            source_file = data_dir / "us_apt.json"
            source_file.write_text(
                json.dumps(
                    [
                        {
                            "name": "MINDEN TAHOE AIRPORT",
                            "icaoCode": "KMEV",
                            "geometry": {"type": "Point", "coordinates": [-119.751, 39.0003]},
                            "elevation": {"value": 1439, "unit": 0},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            cache_path = Path(temp_dir) / "airport-cache.json"
            lookup = AirportLookup(data_dirs=(data_dir,), cache_path=cache_path)

            airport = lookup.find_by_icao("kmev")
            source_file.unlink()
            cached_airport = lookup.find_by_icao("KMEV")

            self.assertEqual(airport, cached_airport)
            self.assertEqual(cached_airport.icao, "KMEV")
            self.assertAlmostEqual(cached_airport.latitude_deg, 39.0003, places=6)
            self.assertAlmostEqual(cached_airport.longitude_deg, -119.751, places=6)
            self.assertAlmostEqual(cached_airport.gps_altitude_m, 1439.0, places=6)

    def test_lookup_finds_place_and_country_from_local_openaip_data(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "openaip"
            data_dir.mkdir()
            (data_dir / "us_apt.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "SAMPLEVILLE AIRPORT",
                            "icaoCode": "KSMP",
                            "country": "US",
                            "geometry": {"type": "Point", "coordinates": [-112.25, 41.50]},
                            "elevation": {"value": 1220, "unit": 0},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            cache_path = Path(temp_dir) / "airport-cache.json"
            lookup = AirportLookup(data_dirs=(data_dir,), cache_path=cache_path)

            airport = lookup.find("Sampleville USA")

            self.assertEqual(airport.icao, "KSMP")
            self.assertEqual(airport.name, "SAMPLEVILLE AIRPORT")
            self.assertAlmostEqual(airport.latitude_deg, 41.50, places=6)
            self.assertAlmostEqual(airport.longitude_deg, -112.25, places=6)
            self.assertAlmostEqual(airport.gps_altitude_m, 1220.0, places=6)


if __name__ == "__main__":
    unittest.main()
