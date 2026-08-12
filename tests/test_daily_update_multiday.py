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
sys.path.insert(0, str(REPO / "scripts"))

import daily_update  # noqa: E402
from init_db import ensure_migrations, init_db  # noqa: E402


class DailyUpdateMultiDayTests(unittest.TestCase):
    def test_existing_database_adds_crawl_run_show_date(self) -> None:
        with sqlite3.connect(":memory:") as conn:
            conn.execute("CREATE TABLE crawl_runs (id INTEGER PRIMARY KEY)")
            conn.execute(
                "CREATE TABLE cinema_locations "
                "(id INTEGER PRIMARY KEY, source_location_code TEXT, notes TEXT)"
            )
            ensure_migrations(conn)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(crawl_runs)")}
        self.assertIn("show_date", columns)

    def _seed_map(self, db: Path) -> tuple[int, int, int]:
        init_db(db)
        with sqlite3.connect(db) as conn:
            chain_id = conn.execute(
                "INSERT INTO cinema_chains (chain_name, official_url) VALUES (?, ?)",
                ("測試影城", "https://example.test"),
            ).lastrowid
            location_id = conn.execute(
                """INSERT INTO cinema_locations
                   (chain_id, location_name, city, latitude, longitude)
                   VALUES (?, ?, ?, ?, ?)""",
                (chain_id, "測試店", "臺北市", 25.0, 121.5),
            ).lastrowid
            movie_id = conn.execute(
                "INSERT INTO movies (title) VALUES (?)", ("測試電影",)
            ).lastrowid
        return int(chain_id), int(location_id), int(movie_id)

    def test_daily_report_only_counts_primary_date_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Path(temp_dir) / "map.sqlite"
            _, _, movie_id = self._seed_map(db)
            with sqlite3.connect(db) as conn:
                conn.executemany(
                    """INSERT INTO crawl_runs
                       (run_type, movie_id, source_name, source_url, show_date,
                        status, rows_found, rows_saved, error_message)
                       VALUES ('showtimes', ?, '同一來源', 'https://example.test', ?, ?, ?, ?, ?)""",
                    [
                        (movie_id, "2026-08-12", "success", 5, 5, None),
                        (movie_id, "2026-08-13", "success", 4, 4, None),
                        (movie_id, "2026-08-14", "failed", 0, 0, "future failed"),
                    ],
                )
            with patch.object(daily_update, "DB_PATH", db):
                sources = daily_update.collect_sources(0, "2026-08-12")
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0]["status"], "success")
            self.assertEqual(sources[0]["found"], 5)
            self.assertEqual(sources[0]["saved"], 5)
            self.assertIsNone(sources[0]["error_message"])

    def test_no_crawl_export_keeps_existing_multiday_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Path(temp_dir) / "map.sqlite"
            output = Path(temp_dir) / "locations.geojson"
            _, location_id, movie_id = self._seed_map(db)
            with sqlite3.connect(db) as conn:
                conn.executemany(
                    """INSERT INTO showtimes
                       (movie_id, location_id, show_date, start_time, source_url)
                       VALUES (?, ?, ?, ?, ?)""",
                    [
                        (movie_id, location_id, "2026-08-12", "20:00", "https://example.test/12"),
                        (movie_id, location_id, "2026-08-13", "10:00", "https://example.test/13"),
                        (movie_id, location_id, "2026-08-14", "11:00", "https://example.test/14"),
                    ],
                )
            with patch.object(daily_update, "DB_PATH", db):
                export_args = daily_update.build_no_crawl_export_args(["測試電影"], "2026-08-12")
            command = [
                sys.executable,
                str(REPO / export_args[0]),
                "--db",
                str(db),
                "--output",
                str(output),
                *export_args[1:],
            ]
            subprocess.run(command, cwd=REPO, check=True, capture_output=True)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["available_dates"],
                ["2026-08-12", "2026-08-13", "2026-08-14"],
            )


if __name__ == "__main__":
    unittest.main()
