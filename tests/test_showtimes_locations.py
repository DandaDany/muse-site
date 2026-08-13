from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from fetch_showtimes_locations import save_locations  # noqa: E402
from init_db import init_db  # noqa: E402


class ShowTimesLocationTests(unittest.TestCase):
    def test_refresh_preserves_existing_master_coordinates(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT_DIR) as temp_dir:
            db_path = Path(temp_dir) / "master.sqlite"
            init_db(db_path)
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "INSERT INTO cinema_chains (chain_name) VALUES (?)",
                    ("秀泰影城",),
                )
                chain_id = conn.execute(
                    "SELECT id FROM cinema_chains WHERE chain_name = ?",
                    ("秀泰影城",),
                ).fetchone()[0]
                conn.execute(
                    """
                    INSERT INTO cinema_locations (
                        chain_id, location_name, latitude, longitude,
                        source_location_code, location_url
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chain_id,
                        "土城秀泰影城",
                        24.97894864459214,
                        121.44515751534473,
                        "old-code",
                        "https://example.test/old",
                    ),
                )

            save_locations(
                [
                    {
                        "location_name": "土城秀泰影城",
                        "address": "新北市土城區學府路二段210號",
                        "city": "新北市",
                        "latitude": 24.9912,
                        "longitude": 121.0439,
                        "source_location_code": "55",
                        "location_url": "https://www.showtimes.com.tw/ticketing?cid=55",
                        "source_url": "https://capi.showtimes.com.tw/4/app/bootstrap",
                        "notes": "test fixture",
                    }
                ],
                db_path,
            )

            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    """
                    SELECT latitude, longitude, source_location_code, location_url
                    FROM cinema_locations
                    WHERE location_name = ?
                    """,
                    ("土城秀泰影城",),
                ).fetchone()

            self.assertEqual(row[0], 24.97894864459214)
            self.assertEqual(row[1], 121.44515751534473)
            self.assertEqual(row[2], "55")
            self.assertEqual(
                row[3],
                "https://www.showtimes.com.tw/ticketing?cid=55",
            )

    def test_refresh_fills_coordinates_for_new_location(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT_DIR) as temp_dir:
            db_path = Path(temp_dir) / "master.sqlite"
            save_locations(
                [
                    {
                        "location_name": "測試新館",
                        "address": "測試地址",
                        "city": "新北市",
                        "latitude": 25.0,
                        "longitude": 121.5,
                        "source_location_code": "new",
                        "location_url": "https://example.test/new",
                        "source_url": "https://capi.showtimes.com.tw/4/app/bootstrap",
                        "notes": "test fixture",
                    }
                ],
                db_path,
            )
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    """
                    SELECT latitude, longitude
                    FROM cinema_locations
                    WHERE location_name = ?
                    """,
                    ("測試新館",),
                ).fetchone()

            self.assertEqual(row, (25.0, 121.5))


if __name__ == "__main__":
    unittest.main()
