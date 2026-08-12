from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import fetch_movie_showtimes as showtimes  # noqa: E402


UCH_HTML = """
<select id="DropDownList1">
  <option value="2026-08-12">2026.08.12</option>
  <option selected="selected" value="2026-08-13">2026.08.13</option>
</select>
<div class="time_box">
  <div class="movie_title">劇場版 吉伊卡哇 人魚島的秘密 (中文發音中文字幕)</div>
  <div class="room_number">6廳</div>
  <ul class="time_item"><li>12:20</li><li>16:30</li></ul>
</div>
"""


class UchMultiDayTests(unittest.TestCase):
    def connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE cinema_chains (id INTEGER PRIMARY KEY, chain_name TEXT);
            CREATE TABLE cinema_locations (
              id INTEGER PRIMARY KEY, chain_id INTEGER, location_name TEXT, active INTEGER DEFAULT 1
            );
            INSERT INTO cinema_chains VALUES (1, '環球中華影城');
            INSERT INTO cinema_locations VALUES (10, 1, '斗六環球中華影城', 1);
            """
        )
        return conn

    def test_postback_selected_date_is_movie_block_date_boundary(self) -> None:
        conn = self.connection()
        with (
            patch.object(showtimes, "render_select_option_html", return_value=UCH_HTML),
            patch.object(showtimes, "save_raw"),
        ):
            records = showtimes.fetch_uch(conn, ["吉伊卡哇"], "2026-08-13")
        self.assertEqual([record.start_time for record in records], ["12:20", "16:30"])
        self.assertTrue(all(record.show_date == "2026-08-13" for record in records))

    def test_postback_date_mismatch_fails_instead_of_mislabeling(self) -> None:
        conn = self.connection()
        wrong_html = UCH_HTML.replace('selected="selected" value="2026-08-13"', 'selected="selected" value="2026-08-12"')
        with (
            patch.object(showtimes, "render_select_option_html", return_value=wrong_html),
            patch.object(showtimes, "save_raw"),
            self.assertRaisesRegex(RuntimeError, "postback mismatch"),
        ):
            showtimes.fetch_uch(conn, ["吉伊卡哇"], "2026-08-13")


if __name__ == "__main__":
    unittest.main()
