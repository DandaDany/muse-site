from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from movie_title_matching import aliases_for_titles, movie_matches, normalize_text  # noqa: E402
from update_map import build_fetch_args  # noqa: E402


class MovieTitleMatchingTest(unittest.TestCase):
    def test_fullwidth_brackets_match_ascii_brackets(self):
        backend = "魔法少女小圓劇場版［新篇］叛逆的物語"
        official = "魔法少女小圓劇場版 [新篇] 叛逆的物語+五分鐘開頭影像"
        self.assertEqual(
            normalize_text(backend),
            "魔法少女小圓劇場版新篇叛逆的物語",
        )
        self.assertTrue(movie_matches(official, [backend]))

    def test_nfkc_handles_fullwidth_latin_and_digits(self):
        self.assertEqual(normalize_text("ＴＯＹ ＳＴＯＲＹ ５"), "toy story 5".replace(" ", ""))
        self.assertTrue(movie_matches("TOY STORY 5 - IMAX", ["ＴＯＹ ＳＴＯＲＹ ５"]))

    def test_backend_aliases_are_loaded_and_deduplicated(self):
        payload = {
            "movies": [
                {
                    "title": "主片名",
                    "aliases": ["別名 A", "別名 A", " 主片名 ", "", None, "別名 B"],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "movie_list.json"
            override_path = Path(temp_dir) / "aliases.json"
            cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            override_path.write_text("{}", encoding="utf-8")
            self.assertEqual(
                aliases_for_titles(["主片名"], cache_path, override_path),
                {"主片名": ["別名 A", "別名 B"]},
            )

    def test_versioned_aliases_supplement_backend_aliases(self):
        payload = {"movies": [{"title": "攻殼機動隊 2026", "aliases": []}]}
        overrides = {
            "攻殼機動隊 2026": [
                "攻殼機動隊(1995) 4K 數位修復版",
                "攻殼機動隊 (1995) 4K數位修復版",
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "movie_list.json"
            override_path = Path(temp_dir) / "aliases.json"
            cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            override_path.write_text(json.dumps(overrides, ensure_ascii=False), encoding="utf-8")
            aliases = aliases_for_titles(["攻殼機動隊 2026"], cache_path, override_path)

        self.assertEqual(aliases["攻殼機動隊 2026"], overrides["攻殼機動隊 2026"])
        self.assertTrue(
            movie_matches(
                "攻殼機動隊(1995) 4K 數位修復版",
                ["攻殼機動隊 2026", *aliases["攻殼機動隊 2026"]],
            )
        )

    def test_missing_cache_is_non_fatal_and_overrides_still_work(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "missing.json"
            override_path = Path(temp_dir) / "aliases.json"
            override_path.write_text(
                json.dumps({"主片名": ["正式片名"]}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertEqual(
                aliases_for_titles(["主片名"], cache_path, override_path),
                {"主片名": ["正式片名"]},
            )

    def test_fetch_args_pass_aliases_and_dates_to_runner(self):
        args = build_fetch_args(
            "主片名",
            ["2026-08-21", "2026-08-22"],
            ["Alias One", "Alias Two"],
        )
        self.assertEqual(args[0:2], ["scripts/fetch_movie_showtimes_runner.py", "主片名"])
        self.assertIn("--alias", args)
        self.assertEqual(args.count("--alias"), 2)
        self.assertEqual(args.count("--date"), 2)
        self.assertIn("2026-08-21", args)
        self.assertIn("2026-08-22", args)


if __name__ == "__main__":
    unittest.main()
