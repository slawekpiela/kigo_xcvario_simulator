import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kigo_xcvario_simulator.airport_lookup import AirportLookup


class AirportLookupTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
