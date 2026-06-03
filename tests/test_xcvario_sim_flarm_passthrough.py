from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from kigo_xcvario_simulator.flarm_passthrough import (
    FlarmPassthroughSimulator,
    load_igc_records_from_directory,
)


class FlarmPassthroughTests(unittest.TestCase):
    def test_packaged_sample_igc_records_are_available_for_logger_download(self):
        sample_dir = Path(__file__).resolve().parents[1] / "kigo_xcvario_simulator" / "examples" / "igc_logs"

        records = load_igc_records_from_directory(sample_dir)
        record_names = {record.source_name for record in records}
        filser_record = next(record for record in records if record.source_name == "18BF14K1.igc")

        self.assertGreaterEqual(len(records), 3)
        self.assertIn("01lz1hq1.igc", record_names)
        self.assertIn("18BF14K1.igc", record_names)
        self.assertIn("9crx3101.igc", record_names)
        self.assertTrue(filser_record.igc_text.startswith("AFIL01460"))
        self.assertTrue(filser_record.record_info.startswith("18BF14K1.igc|2011-08-11|13:53:50|"))

    def test_default_records_prefer_kigo_nav_logs_when_present(self):
        sample_dir = Path(__file__).resolve().parents[1] / "kigo_xcvario_simulator" / "examples" / "igc_logs"
        with TemporaryDirectory() as tmp_dir:
            logs_dir = Path(tmp_dir)
            (logs_dir / "local-log.igc").write_text(
                "\n".join(
                    [
                        "AXCSSIM",
                        "HFDTE030626",
                        "HFPLTPILOTINCHARGE:LOCAL PILOT",
                        "B1200004983000N01900202EA0040100401",
                        "B1215004983100N01900500EA0045000450",
                    ]
                ),
                encoding="ascii",
            )

            with patch(
                "kigo_xcvario_simulator.flarm_passthrough._kigo_nav_logs_dir",
                return_value=logs_dir,
            ), patch(
                "kigo_xcvario_simulator.flarm_passthrough._packaged_igc_logs_dir",
                return_value=sample_dir,
            ):
                simulator = FlarmPassthroughSimulator()

        self.assertEqual(simulator.record_names, ("local-log.igc",))
        self.assertEqual(simulator.record_count, 1)


if __name__ == "__main__":
    unittest.main()
