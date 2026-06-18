import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, urlparse

from kigo_xcvario_simulator.airport_lookup import AirportLookup


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return None

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class _FakeUrlopen:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []
        self.timeouts = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        return _FakeResponse(self.payload)


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

    def test_free_text_location_uses_online_geocoder_and_caches_result(self):
        with TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "airport-cache.json"
            fake_urlopen = _FakeUrlopen(
                [
                    {
                        "display_name": "Minden-Tahoe Airport, Douglas County, Nevada, United States",
                        "lat": "39.0003",
                        "lon": "-119.751",
                    }
                ]
            )
            lookup = AirportLookup(
                data_dirs=(Path(temp_dir) / "missing",),
                cache_path=cache_path,
                geocoder_search_url="https://example.test/search",
                urlopen_func=fake_urlopen,
            )

            airport = lookup.find("MINDen tahoe USA")
            cached_airport = lookup.find("MINDen tahoe USA")

            self.assertEqual(airport, cached_airport)
            self.assertEqual(airport.icao, "GEOCODE")
            self.assertEqual(airport.name, "Minden-Tahoe Airport, Douglas County, Nevada, United States")
            self.assertAlmostEqual(airport.latitude_deg, 39.0003, places=6)
            self.assertAlmostEqual(airport.longitude_deg, -119.751, places=6)
            self.assertAlmostEqual(airport.gps_altitude_m, 0.0, places=6)
            self.assertEqual(len(fake_urlopen.requests), 1)

            request = fake_urlopen.requests[0]
            params = parse_qs(urlparse(request.full_url).query)
            self.assertEqual(params["q"], ["MINDen tahoe USA"])
            self.assertEqual(params["format"], ["jsonv2"])
            self.assertEqual(params["limit"], ["1"])
            self.assertEqual(params["countrycodes"], ["us"])
            self.assertIn("kigo-xcvario-simulator", request.get_header("User-agent"))

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

    def test_free_text_location_without_result_raises_value_error(self):
        with TemporaryDirectory() as temp_dir:
            lookup = AirportLookup(
                data_dirs=(Path(temp_dir) / "missing",),
                cache_path=Path(temp_dir) / "airport-cache.json",
                urlopen_func=_FakeUrlopen([]),
            )

            with self.assertRaisesRegex(ValueError, "found no result"):
                lookup.find("Nowhere USA")


if __name__ == "__main__":
    unittest.main()
