from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import fetch_movie_showtimes as showtimes  # noqa: E402


def atmovies_html(title: str, times: list[str], version: str) -> str:
    time_items = "".join(f"<li>{value}</li>" for value in times)
    return f"""
        <h3>2026/08/02 (日)</h3>
        <div id="theaterShowtimeBlock">
          <ul id="theaterShowtimeTable">
            <li class="filmTitle">{title}</li>
            <li><ul><li class="filmVersion">{version}</li>{time_items}</ul></li>
          </ul>
        </div>
    """


class SmallCinemaFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE cinema_chains (id INTEGER PRIMARY KEY, chain_name TEXT);
            CREATE TABLE cinema_locations (
                id INTEGER PRIMARY KEY,
                chain_id INTEGER,
                location_url TEXT,
                source_url TEXT,
                source_location_code TEXT,
                active INTEGER
            );
            INSERT INTO cinema_chains VALUES (1, '王牌映画影城');
            INSERT INTO cinema_chains VALUES (2, '中影屏東影城');
            INSERT INTO cinema_locations VALUES
                (11, 1, 'https://www.acecinema.com.tw/movie/now', NULL, 'main', 1),
                (12, 2, 'https://ptcinema.movie.com.tw/time', NULL, 'main', 1);
            """
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_ace_uses_atmovies_when_official_request_fails(self) -> None:
        fallback_html = atmovies_html("玩具總動員5", ["16：10"], "中文版")
        with (
            patch.object(showtimes, "request_bytes", side_effect=OSError("official timeout")),
            patch.object(showtimes, "request_atmovies_text", return_value=fallback_html),
        ):
            records = showtimes.fetch_acecinema(
                self.conn, ["玩具總動員5", "Toy Story 5"], "2026-08-02"
            )

        self.assertEqual([record.start_time for record in records], ["16:10"])
        self.assertEqual(records[0].booking_url, showtimes.ACE_URL)
        self.assertEqual(records[0].source_url, showtimes.ACE_ATMOVIES_URL)

    def test_ptcinema_uses_atmovies_when_official_dns_fails(self) -> None:
        fallback_html = atmovies_html(
            "名偵探柯南 高速公路的墮天使",
            ["12：20", "16：20", "18：20"],
            "日文版",
        )
        with (
            patch.object(showtimes, "request_bytes", side_effect=OSError("DNS resolution failed")),
            patch.object(showtimes, "request_atmovies_text", return_value=fallback_html),
        ):
            records = showtimes.fetch_ptcinema(
                self.conn,
                ["名偵探柯南：高速公路的墮天使", "名偵探柯南 高速公路的墮天使"],
                "2026-08-02",
            )

        self.assertEqual([record.start_time for record in records], ["12:20", "16:20", "18:20"])
        self.assertEqual(records[0].booking_url, "https://ptcinema.movie.com.tw/time?date=2026-08-02")
        self.assertEqual(records[0].source_url, showtimes.PTCINEMA_ATMOVIES_URL)


if __name__ == "__main__":
    unittest.main()
