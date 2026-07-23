from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
import gc
import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import fetch_movie_showtimes as showtimes  # noqa: E402
from import_cinema_sources import overlay_existing_locations  # noqa: E402
from init_db import init_db  # noqa: E402
from verify_cinema_codes import verify_codes  # noqa: E402
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # noqa: E402


SK_LOCATIONS = [
    ("新光影城台中中港", "1003"),
    ("新光影城台北天母", "1005"),
    ("新光影城台北獅子林", "1001"),
    ("新光影城台南西門", "1002"),
    ("新光影城桃園青埔", "1004"),
]


def make_db(path: Path, *, with_codes: bool = False) -> None:
    init_db(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("INSERT INTO cinema_chains (chain_name) VALUES ('新光影城')")
        chain_id = conn.execute("SELECT id FROM cinema_chains WHERE chain_name = '新光影城'").fetchone()[0]
        for index, (name, code) in enumerate(SK_LOCATIONS):
            conn.execute(
                """
                INSERT INTO cinema_locations
                    (chain_id, location_name, address, latitude, longitude, source_location_code)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chain_id, name, f"測試地址 {index}", 25 + index / 100, 121 + index / 100, code if with_codes else None),
            )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def workspace_tempdir():
    # The test runner may not be allowed to write to the system temp directory.
    temp_dir = tempfile.TemporaryDirectory(dir=PROJECT_DIR)
    try:
        yield temp_dir.name
    finally:
        # sqlite3 connection context managers commit transactions but do not
        # close the handle; collect short-lived helpers before Windows cleanup.
        gc.collect()
        temp_dir.cleanup()


class ShinKongResilienceTests(unittest.TestCase):
    ATMOVIES_PAGE = """
    <h3>2026/07/23 (四)</h3>
    <div id="theaterShowtimeBlock">
      <ul id="theaterShowtimeTable">
        <li class="filmTitle">無關電影</li><li><ul><li>09：00</li></ul></li>
      </ul>
      <ul id="theaterShowtimeTable">
        <li class="filmTitle">玩具總動員5</li><li>
          <ul><li><img src="poster.jpg" /></li><li>片長：102分</li></ul>
          <ul><li class="filmVersion">英文版</li><li>19：20</li><li class="theaterElse">其他戲院</li></ul>
          <ul><li class="filmVersion">國語版</li><li>21:30(隔日)</li></ul>
        </li>
      </ul>
      <ul id="theaterShowtimeTable">
        <li class="filmTitle">名偵探柯南 高速公路的墮天使</li><li>
          <ul><li>14：10</li><li>19：35</li><li class="theaterElse">其他戲院</li></ul>
        </li>
      </ul>
    </div>
    """

    @staticmethod
    def atmovies_row() -> dict[str, object]:
        return {"id": 1, "source_location_code": "1001"}

    def test_atmovies_parser_keeps_movie_and_version_boundaries(self) -> None:
        records = showtimes.parse_skcinemas_atmovies_page(
            self.ATMOVIES_PAGE,
            self.atmovies_row(),
            ["玩具總動員5", "玩具總動員 5"],
            "2026-07-23",
            "https://example.test/showtime/",
        )
        self.assertEqual([(item.start_time, item.format, item.language) for item in records], [
            ("19:20", "英文版", "英語"),
            ("21:30", "國語版", "國語"),
        ])
        self.assertTrue(all("@movies" in item.raw_text for item in records))

    def test_atmovies_parser_uses_japanese_default_when_version_is_absent(self) -> None:
        records = showtimes.parse_skcinemas_atmovies_page(
            self.ATMOVIES_PAGE,
            self.atmovies_row(),
            ["名偵探柯南"],
            "2026-07-23",
            "https://example.test/showtime/",
        )
        self.assertEqual([(item.start_time, item.format, item.language) for item in records], [
            ("14:10", "日語版", "日語"),
            ("19:35", "日語版", "日語"),
        ])

    def test_atmovies_parser_rejects_date_mismatch(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "atmovies_date_mismatch"):
            showtimes.parse_skcinemas_atmovies_page(
                self.ATMOVIES_PAGE, self.atmovies_row(), ["玩具總動員5"], "2026-07-24", "https://example.test/"
            )

    def test_atmovies_request_retries_then_returns_text(self) -> None:
        with patch.object(
            showtimes, "request_text", side_effect=[RuntimeError("502"), RuntimeError("502"), "page"]
        ), patch.object(showtimes.time, "sleep") as sleep:
            self.assertEqual(showtimes.request_atmovies_text("https://example.test/"), "page")
        self.assertEqual(sleep.call_count, 2)

    def test_all_active_shin_kong_codes_have_atmovies_mapping(self) -> None:
        self.assertEqual(set(showtimes.SKCINEMAS_ATMOVIES), {"1001", "1002", "1003", "1004", "1005"})

    def test_unreachable_official_source_uses_atmovies_without_playwright(self) -> None:
        with workspace_tempdir() as temp_dir:
            db_path = Path(temp_dir) / "master.sqlite"
            make_db(db_path, with_codes=True)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                with patch.dict(os.environ, {"SKCINEMAS_OFFICIAL_REACHABLE": "false"}), patch.object(
                    showtimes, "fetch_skcinemas_atmovies", return_value=[]
                ) as fallback, patch.object(showtimes, "capture_skcinemas_headers") as official:
                    self.assertEqual(showtimes.fetch_skcinemas(conn, ["玩具總動員5"], "2026-07-23"), [])
                fallback.assert_called_once()
                official.assert_not_called()
            finally:
                conn.close()

    def test_official_and_atmovies_failures_return_valid_zero(self) -> None:
        with workspace_tempdir() as temp_dir:
            db_path = Path(temp_dir) / "master.sqlite"
            make_db(db_path, with_codes=True)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                with patch.dict(os.environ, {"SKCINEMAS_OFFICIAL_REACHABLE": ""}), patch.object(
                    showtimes, "capture_skcinemas_headers", side_effect=RuntimeError("official_down")
                ), patch.object(showtimes, "fetch_skcinemas_atmovies", side_effect=RuntimeError("fallback_down")):
                    self.assertEqual(showtimes.fetch_skcinemas(conn, ["玩具總動員5"], "2026-07-23"), [])
            finally:
                conn.close()

    def test_offline_atmovies_failure_returns_valid_zero(self) -> None:
        with workspace_tempdir() as temp_dir:
            db_path = Path(temp_dir) / "master.sqlite"
            make_db(db_path, with_codes=True)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                with patch.dict(os.environ, {"SKCINEMAS_OFFICIAL_REACHABLE": "false"}), patch.object(
                    showtimes, "fetch_skcinemas_atmovies", side_effect=RuntimeError("fallback_down")
                ), patch.object(showtimes, "capture_skcinemas_headers") as official:
                    self.assertEqual(showtimes.fetch_skcinemas(conn, ["玩具總動員5"], "2026-07-23"), [])
                official.assert_not_called()
            finally:
                conn.close()

    def test_versioned_codes_overlay_preserves_master_location_fields(self) -> None:
        with workspace_tempdir() as temp_dir:
            db_path = Path(temp_dir) / "master.sqlite"
            make_db(db_path)
            updated, missing = overlay_existing_locations(
                PROJECT_DIR / "data" / "input" / "cinema_codes.csv",
                db_path,
                require_existing=True,
                chain_names={"新光影城"},
            )
            self.assertEqual(updated, 5)
            self.assertEqual(missing, 0)
            self.assertEqual(verify_codes(PROJECT_DIR / "data" / "input" / "cinema_codes.csv", db_path, "新光影城"), 5)
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    "SELECT location_name, address, latitude, longitude, source_location_code "
                    "FROM cinema_locations ORDER BY location_name"
                ).fetchall()
            finally:
                conn.close()
            self.assertEqual(len(rows), 5)
            self.assertTrue(all(row[1] and row[2] is not None and row[3] is not None for row in rows))
            self.assertEqual({row[4] for row in rows}, {code for _, code in SK_LOCATIONS})

    def test_active_shin_kong_without_codes_is_a_configuration_error(self) -> None:
        with workspace_tempdir() as temp_dir:
            db_path = Path(temp_dir) / "master.sqlite"
            make_db(db_path)
            conn = sqlite3.connect(db_path)
            try:
                conn.row_factory = sqlite3.Row
                with self.assertRaisesRegex(RuntimeError, "0 個據點具有 source_location_code"):
                    showtimes.fetch_skcinemas(conn, ["測試電影"], "2026-07-23")
            finally:
                conn.close()

    def test_timeout_with_captured_headers_is_recoverable(self) -> None:
        timeout = PlaywrightTimeoutError("navigation timed out")
        self.assertTrue(showtimes.navigation_timeout_is_recoverable(timeout, {"token": "x"}))
        self.assertFalse(showtimes.navigation_timeout_is_recoverable(timeout, {}))
        self.assertEqual(
            showtimes.skcinemas_headers_from_request(
                {"Timestamp": "1", "DID": "device", "Token": "secret"}, "https://example.test/films"
            )["DID"],
            "device",
        )

    def test_normal_api_response_without_target_movie_is_a_valid_zero(self) -> None:
        with workspace_tempdir() as temp_dir:
            db_path = Path(temp_dir) / "master.sqlite"
            make_db(db_path, with_codes=True)
            conn = sqlite3.connect(db_path)
            try:
                conn.row_factory = sqlite3.Row
                with patch.object(showtimes, "capture_skcinemas_headers", return_value={"token": "x"}), patch.object(
                    showtimes, "request_json", return_value={"result": True, "data": {"SessionFilm": [], "Session": []}}
                ), patch.object(showtimes, "save_raw"):
                    self.assertEqual(showtimes.fetch_skcinemas(conn, ["不存在的電影"], "2026-07-23"), [])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
