from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import daily_update  # noqa: E402
import muse_api  # noqa: E402
import update_map  # noqa: E402


class EmptyMovieStateTests(unittest.TestCase):
    def test_pull_movie_list_accepts_explicit_zero_from_api(self) -> None:
        payload = {
            "generated_at": "2026-08-20T08:00:00+00:00",
            "version": 0,
            "count": 0,
            "movies": [],
        }
        with (
            patch.object(muse_api, "api_base", return_value="https://example.test"),
            patch.object(muse_api, "_request", return_value=(200, payload)),
            patch.object(muse_api, "_update_cache") as update_cache,
        ):
            movies, meta = muse_api.pull_movie_list()

        self.assertEqual(movies, [])
        self.assertEqual(meta["source"], "api")
        self.assertEqual(meta["count"], 0)
        self.assertEqual(meta["cache_age_seconds"], 0)
        update_cache.assert_called_once_with(payload)

    def test_write_movie_list_txt_can_clear_the_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            movie_list = Path(temp_dir) / "電影清單.txt"
            with patch.object(muse_api, "MOVIE_LIST", movie_list):
                muse_api.write_movie_list_txt([])
            self.assertEqual(movie_list.read_text(encoding="utf-8-sig"), "")

    def test_empty_map_payload_contains_no_old_movie_or_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "locations.geojson"
            update_map.write_empty_movie_map("2026-08-20", output)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["empty_state"], "no_movies_today")
        self.assertEqual(payload["show_date"], "2026-08-20")
        self.assertEqual(payload["movies"], [])
        self.assertEqual(payload["movie_features"], {})
        self.assertEqual(payload["movie_features_by_date"], {})
        self.assertEqual(payload["available_dates"], [])
        self.assertEqual(payload["features"], [])
        self.assertEqual(payload["feature_count"], 0)

    def test_zero_movie_daily_run_is_success(self) -> None:
        summary = {
            "sources_total": 0,
            "sources_success": 0,
            "sources_failed": 0,
        }
        self.assertEqual(daily_update.overall_status(summary, True, 0), "success")
        self.assertEqual(daily_update.overall_status(summary, False, 0), "success")


if __name__ == "__main__":
    unittest.main()
