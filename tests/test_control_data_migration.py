from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import control_data  # noqa: E402
import daily_update  # noqa: E402
import migrate_control_plane  # noqa: E402


def tracked_payload():
    return {
        "schema_version": 1,
        "version": 123,
        "movies": [
            {
                "id": 1,
                "title": "today",
                "aliases": ["official title"],
                "target_date": "2026-09-03",
                "is_active": True,
                "sort_order": 2,
                "notes": "",
                "updated_at": "2026-09-01T00:00:00+08:00",
            },
            {
                "id": 2,
                "title": "day7",
                "aliases": [],
                "target_date": "2026-09-10",
                "is_active": True,
                "sort_order": 1,
                "notes": "",
            },
            {
                "id": 3,
                "title": "day8",
                "aliases": [],
                "target_date": "2026-09-11",
                "is_active": True,
                "sort_order": 3,
                "notes": "",
            },
            {
                "id": 4,
                "title": "inactive",
                "aliases": [],
                "target_date": None,
                "is_active": False,
                "sort_order": 0,
                "notes": "",
            },
        ],
    }


def cinema_payload():
    return {
        "schema_version": 1,
        "chains": [
            {
                "id": 10,
                "chain_name": "A",
                "official_url": None,
                "crawl_url": None,
                "booking_url": None,
                "all_locations_assumed_showing": True,
                "notes": None,
                "active": True,
            },
            {
                "id": 20,
                "chain_name": "B",
                "official_url": None,
                "crawl_url": None,
                "booking_url": None,
                "all_locations_assumed_showing": True,
                "notes": None,
                "active": False,
            },
        ],
        "locations": [
            {
                "id": 100,
                "chain_id": 10,
                "location_name": "L1",
                "display_name": None,
                "address": None,
                "city": None,
                "district": None,
                "latitude": 1.0,
                "longitude": 2.0,
                "source_location_code": "old",
                "location_url": None,
                "source_url": None,
                "notes": None,
                "active": True,
            },
            {
                "id": 200,
                "chain_id": 20,
                "location_name": "L2",
                "display_name": None,
                "address": None,
                "city": None,
                "district": None,
                "latitude": None,
                "longitude": None,
                "source_location_code": None,
                "location_url": None,
                "source_url": None,
                "notes": None,
                "active": False,
            },
        ],
    }


class ControlDataMigrationTest(unittest.TestCase):
    def test_movie_horizon_matches_backend_boundary(self):
        movies = control_data.eligible_movies(tracked_payload(), date(2026, 9, 3))
        self.assertEqual([m["title"] for m in movies], ["day7", "today"])

    def test_runtime_movie_cache_preserves_aliases(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = control_data.write_runtime_movie_files(
                tracked_payload(),
                date(2026, 9, 3),
                root / "電影清單.txt",
                root / "tracked_movies.json",
            )
            self.assertEqual(runtime["count"], 2)
            self.assertEqual(runtime["movies"][1]["aliases"], ["official title"])

    def test_active_cinema_view_matches_backend_semantics(self):
        runtime = control_data.active_cinema_payload(cinema_payload())
        self.assertEqual(runtime["chain_count"], 1)
        self.assertEqual(runtime["location_count"], 1)
        self.assertEqual(runtime["chains"][0]["chain_name"], "A")
        self.assertEqual(runtime["locations"][0]["location_name"], "L1")

    def test_sqlite_rebuild_is_row_for_row_equivalent(self):
        canonical = cinema_payload()
        legacy = control_data.active_cinema_payload(canonical)
        migrate_control_plane.assert_sqlite_parity(canonical, legacy)

    def test_sqlite_parity_detects_a_master_difference(self):
        canonical = cinema_payload()
        legacy = control_data.active_cinema_payload(canonical)
        legacy["locations"][0] = dict(legacy["locations"][0])
        legacy["locations"][0]["source_location_code"] = "different"
        with self.assertRaises(ValueError):
            migrate_control_plane.assert_sqlite_parity(canonical, legacy)

    def test_dynamic_code_persists_and_blank_refresh_does_not_erase_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            master = root / "cinema_master.json"
            master.write_text(json.dumps(cinema_payload()), encoding="utf-8")
            db = root / "movie_map.sqlite"
            con = sqlite3.connect(db)
            con.executescript(
                """
                CREATE TABLE cinema_chains(id INTEGER PRIMARY KEY, chain_name TEXT);
                CREATE TABLE cinema_locations(
                    id INTEGER PRIMARY KEY,
                    chain_id INTEGER,
                    location_name TEXT,
                    source_location_code TEXT
                );
                INSERT INTO cinema_chains VALUES(10, 'A');
                INSERT INTO cinema_locations VALUES(100, 10, 'L1', 'new-code');
                """
            )
            con.commit()
            con.close()

            updated, skipped = control_data.persist_codes_from_sqlite(db, master)
            self.assertEqual((updated, skipped), (1, 0))
            self.assertEqual(
                json.loads(master.read_text(encoding="utf-8"))["locations"][0]["source_location_code"],
                "new-code",
            )

            con = sqlite3.connect(db)
            con.execute("UPDATE cinema_locations SET source_location_code = '' WHERE id = 100")
            con.commit()
            con.close()
            updated, skipped = control_data.persist_codes_from_sqlite(db, master)
            self.assertEqual((updated, skipped), (0, 0))
            self.assertEqual(
                json.loads(master.read_text(encoding="utf-8"))["locations"][0]["source_location_code"],
                "new-code",
            )

    def test_invalid_master_fails_closed(self):
        payload = cinema_payload()
        payload["locations"][0]["chain_id"] = 999
        with self.assertRaises(ValueError):
            control_data.validate_cinema_master(payload)

    def test_half_migrated_control_plane_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tracked = root / "tracked_movies.json"
            cinema = root / "cinema_master.json"
            tracked.write_text("{}", encoding="utf-8")
            with patch.object(daily_update.control_data, "TRACKED_MOVIES_PATH", tracked), patch.object(
                daily_update.control_data, "CINEMA_MASTER_PATH", cinema
            ):
                with self.assertRaises(RuntimeError):
                    daily_update.git_control_enabled()


if __name__ == "__main__":
    unittest.main()
