from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
FIXTURES = REPO / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))

import fetch_movie_showtimes as showtimes  # noqa: E402
from init_db import init_db  # noqa: E402


SHOW_DATE = "2026-08-13"
MOVIE = "測試雙語電影"
AMBASSADOR_URL = showtimes.ambassador_url("amb-test", SHOW_DATE)


class AmbassadorHalarRegressionTests(unittest.TestCase):
    def _seed_db(self, db: Path) -> tuple[int, int, int]:
        init_db(db)
        with sqlite3.connect(db) as conn:
            ambassador_chain = conn.execute(
                "INSERT INTO cinema_chains (chain_name, official_url) VALUES (?, ?)",
                ("國賓影城", "https://www.ambassador.com.tw/"),
            ).lastrowid
            halar_chain = conn.execute(
                "INSERT INTO cinema_chains (chain_name, official_url) VALUES (?, ?)",
                ("哈拉影城", showtimes.HALAR_URL),
            ).lastrowid
            ambassador_location = conn.execute(
                """INSERT INTO cinema_locations
                   (chain_id, location_name, city, latitude, longitude, source_location_code)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (ambassador_chain, "國賓測試館", "臺北市", 25.0, 121.5, "amb-test"),
            ).lastrowid
            halar_location = conn.execute(
                """INSERT INTO cinema_locations
                   (chain_id, location_name, city, latitude, longitude, location_url)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (halar_chain, "哈拉影城", "臺北市", 25.1, 121.6, "https://legacy.test/wrong"),
            ).lastrowid
            movie_id = conn.execute("INSERT INTO movies (title) VALUES (?)", (MOVIE,)).lastrowid
        return int(ambassador_location), int(halar_location), int(movie_id)

    def test_ambassador_groups_each_language_with_its_own_seat_list(self) -> None:
        html = (FIXTURES / "ambassador_multilanguage.html").read_text(encoding="utf-8")
        location = {"id": 11, "source_location_code": "amb-test"}
        with patch.object(showtimes, "request_text", return_value=html), patch.object(showtimes, "save_raw"):
            records = showtimes.fetch_ambassador_location(location, [MOVIE], SHOW_DATE)

        self.assertEqual(
            [(r.start_time, r.format, r.language) for r in sorted(records, key=lambda r: r.start_time)],
            [
                ("10:50", "(數位‧日文版)測試雙語電影", "日語"),
                ("15:15", "(數位‧日文版)測試雙語電影", "日語"),
                ("17:20", "(數位‧中文版)測試雙語電影", "國語"),
                ("19:00", "(數位‧日文版)測試雙語電影", "日語"),
            ],
        )
        self.assertTrue(all(r.show_date == SHOW_DATE for r in records))
        self.assertTrue(all(r.booking_url == AMBASSADOR_URL for r in records))
        self.assertTrue(all(r.source_url == AMBASSADOR_URL for r in records))

    def test_clean_crawl_save_and_export_preserves_languages_and_halar_url(self) -> None:
        ambassador_html = (FIXTURES / "ambassador_multilanguage.html").read_text(encoding="utf-8")
        halar_html = (FIXTURES / "halar_wrong_session_link.html").read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Path(temp_dir) / "fresh.sqlite"
            output = Path(temp_dir) / "fresh.geojson"
            ambassador_id, halar_id, movie_id = self._seed_db(db)
            with sqlite3.connect(db) as conn:
                conn.row_factory = sqlite3.Row
                ambassador_location = conn.execute(
                    "SELECT * FROM cinema_locations WHERE id = ?", (ambassador_id,)
                ).fetchone()
                with patch.object(showtimes, "request_text", return_value=ambassador_html), patch.object(
                    showtimes, "request_bytes", return_value=halar_html
                ), patch.object(showtimes, "save_raw"):
                    ambassador_records = showtimes.fetch_ambassador_location(
                        ambassador_location, [MOVIE], SHOW_DATE
                    )
                    halar_records = showtimes.fetch_halar(conn, [MOVIE], SHOW_DATE)

                ambassador_run = showtimes.start_run(
                    conn, movie_id, "國賓影城", AMBASSADOR_URL, SHOW_DATE
                )
                halar_run = showtimes.start_run(
                    conn, movie_id, "哈拉影城", showtimes.HALAR_URL, SHOW_DATE
                )
                showtimes.save_showtimes(conn, movie_id, ambassador_run, ambassador_records)
                showtimes.save_showtimes(conn, movie_id, halar_run, halar_records)

            self.assertEqual(len(halar_records), 1)
            self.assertEqual(halar_records[0].booking_url, showtimes.HALAR_URL)
            self.assertEqual(halar_records[0].source_url, showtimes.HALAR_URL)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "export_geojson.py"),
                    "--db", str(db),
                    "--output", str(output),
                    "--movie-title", MOVIE,
                    "--date", SHOW_DATE,
                ],
                cwd=REPO,
                check=True,
                capture_output=True,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            features = payload["features"]
            ambassador = next(f for f in features if f["properties"]["chain_name"] == "國賓影城")
            halar = next(f for f in features if f["properties"]["chain_name"] == "哈拉影城")

            self.assertEqual(
                [(s["time"], s["format"], s["language"]) for s in ambassador["properties"]["showtimes"]],
                [
                    ("10:50", "(數位‧日文版)測試雙語電影", "日語"),
                    ("15:15", "(數位‧日文版)測試雙語電影", "日語"),
                    ("17:20", "(數位‧中文版)測試雙語電影", "國語"),
                    ("19:00", "(數位‧日文版)測試雙語電影", "日語"),
                ],
            )
            self.assertEqual(halar["properties"]["location_url"], showtimes.HALAR_URL)


if __name__ == "__main__":
    unittest.main()
