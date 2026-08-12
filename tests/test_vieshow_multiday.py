from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fetch_movie_showtimes import records_from_text_block


class VieshowMultiDayTests(unittest.TestCase):
    def test_only_requested_date_section_is_returned(self) -> None:
        text = """
        玩具總動員5
        8/12（三）
        國語 10:00 12:20
        8/13（四）
        國語 09:30 18:40
        """

        records = records_from_text_block(
            location_id=1,
            show_date="2026-08-13",
            text=text,
            aliases=["玩具總動員5"],
            source_url="https://www.vscinemas.com.tw/",
            booking_url="https://www.vscinemas.com.tw/",
            strict_date_sections=True,
        )

        self.assertEqual([record.start_time for record in records], ["09:30", "18:40"])
        self.assertTrue(all(record.show_date == "2026-08-13" for record in records))


if __name__ == "__main__":
    unittest.main()
