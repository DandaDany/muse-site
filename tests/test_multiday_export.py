from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime
import tempfile
import unittest
from pathlib import Path


class MultiDayExportTests(unittest.TestCase):
    def test_new_contract_keeps_primary_date_legacy_fields(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Path(temp_dir) / "map.sqlite"
            output = Path(temp_dir) / "locations.geojson"
            subprocess.run(
                [sys.executable, str(repo / "scripts" / "init_db.py"), "--db", str(db)],
                check=True,
                cwd=repo,
                capture_output=True,
            )
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
                conn.executemany(
                    """INSERT INTO showtimes
                       (movie_id, location_id, show_date, start_time, source_url)
                       VALUES (?, ?, ?, ?, ?)""",
                    [
                        (movie_id, location_id, "2026-08-12", "20:00", "https://example.test/12"),
                        (movie_id, location_id, "2026-08-13", "10:00", "https://example.test/13"),
                    ],
                )
            subprocess.run(
                [
                    sys.executable,
                    str(repo / "scripts" / "export_geojson.py"),
                    "--db",
                    str(db),
                    "--output",
                    str(output),
                    "--movie-title",
                    "測試電影",
                    "--date",
                    "2026-08-12",
                    "--additional-date",
                    "2026-08-13",
                ],
                check=True,
                cwd=repo,
                capture_output=True,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["available_dates"], ["2026-08-12", "2026-08-13"])
            self.assertRegex(
                payload["updated_at"],
                r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+08:00$",
            )
            self.assertEqual(
                datetime.fromisoformat(payload["updated_at"]).utcoffset().total_seconds(),
                8 * 60 * 60,
            )
            self.assertEqual(payload["features"], payload["movie_features"]["測試電影"])
            self.assertEqual(
                payload["movie_features_by_date"]["測試電影"]["2026-08-13"][0]["properties"]["show_date"],
                "2026-08-13",
            )

    def test_legacy_single_day_payload_remains_supported(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Path(temp_dir) / "map.sqlite"
            output = Path(temp_dir) / "locations.geojson"
            subprocess.run(
                [sys.executable, str(repo / "scripts" / "init_db.py"), "--db", str(db)],
                check=True,
                cwd=repo,
                capture_output=True,
            )
            with sqlite3.connect(db) as conn:
                chain_id = conn.execute(
                    "INSERT INTO cinema_chains (chain_name) VALUES (?)", ("測試影城",)
                ).lastrowid
                location_id = conn.execute(
                    """INSERT INTO cinema_locations
                       (chain_id, location_name, latitude, longitude)
                       VALUES (?, ?, ?, ?)""",
                    (chain_id, "測試店", 25.0, 121.5),
                ).lastrowid
                movie_id = conn.execute(
                    "INSERT INTO movies (title) VALUES (?)", ("單日電影",)
                ).lastrowid
                conn.execute(
                    """INSERT INTO showtimes
                       (movie_id, location_id, show_date, start_time)
                       VALUES (?, ?, ?, ?)""",
                    (movie_id, location_id, "2026-08-12", "20:00"),
                )
            subprocess.run(
                [
                    sys.executable,
                    str(repo / "scripts" / "export_geojson.py"),
                    "--db",
                    str(db),
                    "--output",
                    str(output),
                    "--movie-title",
                    "單日電影",
                    "--date",
                    "2026-08-12",
                ],
                check=True,
                cwd=repo,
                capture_output=True,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["available_dates"], ["2026-08-12"])
            self.assertEqual(payload["features"], payload["movie_features"]["單日電影"])


if __name__ == "__main__":
    unittest.main()
