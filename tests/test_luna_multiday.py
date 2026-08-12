from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_movie_showtimes as showtimes  # noqa: E402


LUNA_HTML = """
<table id="DataList1">
  <tr><td>
    <span id="DataList1_ctl00_SHOW_DATELabel">2026/08/12 星期三</span>
    <table><tr><td><span id="DataList1_ctl00_DataList2_ctl00_SCREEN_NAMELabel">1廳</span></td>
    <td><table><tr><td><span id="DataList1_ctl00_NAME_CHTLabel">測試電影</span></td>
    <td><span id="DataList1_ctl00_TIMELabel">20:10</span></td></tr></table></td></tr></table>
  </td></tr>
  <tr><td>
    <span id="DataList1_ctl01_SHOW_DATELabel">2026/08/13 星期四</span>
    <table><tr><td><span id="DataList1_ctl01_DataList2_ctl00_SCREEN_NAMELabel">2廳</span></td>
    <td><table><tr><td><span id="DataList1_ctl01_NAME_CHTLabel">測試電影</span></td>
    <td><span id="DataList1_ctl01_TIMELabel">10:20</span></td></tr></table></td></tr></table>
  </td></tr>
</table>
""".encode()


class LunaMultiDayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE cinema_chains (id INTEGER PRIMARY KEY, chain_name TEXT);
            CREATE TABLE cinema_locations (
              id INTEGER PRIMARY KEY, chain_id INTEGER, location_name TEXT, active INTEGER DEFAULT 1
            );
            INSERT INTO cinema_chains VALUES (1, '新月豪華影城');
            INSERT INTO cinema_locations VALUES (10, 1, '新月豪華影城', 1);
            """
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_dates_are_not_cross_assigned(self) -> None:
        with patch.object(showtimes, "request_bytes", return_value=LUNA_HTML), patch.object(
            showtimes, "save_raw"
        ):
            today = showtimes.fetch_luna(self.conn, ["測試電影"], "2026-08-12")
            tomorrow = showtimes.fetch_luna(self.conn, ["測試電影"], "2026-08-13")
        self.assertEqual([(item.show_date, item.start_time) for item in today], [("2026-08-12", "20:10")])
        self.assertEqual([(item.show_date, item.start_time) for item in tomorrow], [("2026-08-13", "10:20")])


if __name__ == "__main__":
    unittest.main()
