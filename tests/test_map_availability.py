from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from map_availability import sanitize_movie_availability  # noqa: E402


def feature(title: str, show_date: str, count: int, *, unavailable: bool = False) -> dict:
    props = {
        "movie_title": title,
        "show_date": show_date,
        "showtime_count": count,
        "showtimes": [{"time": "18:00"}] * count,
    }
    if unavailable:
        props["showtime_unavailable"] = True
        props["showtime_unavailable_reason"] = "temporary source failure"
    return {"type": "Feature", "geometry": None, "properties": props}


class MapAvailabilityTest(unittest.TestCase):
    def test_fallback_only_upcoming_movies_do_not_become_default(self):
        today = "2026-09-01"
        payload = {
            "show_date": today,
            "movies": [
                {"title": "未上映 A", "feature_count": 1, "available_dates": [today]},
                {"title": "未上映 B", "feature_count": 1, "available_dates": [today]},
                {"title": "上映中 C", "feature_count": 2, "available_dates": [today]},
            ],
            "movie_features": {},
            "movie_features_by_date": {
                "未上映 A": {today: [feature("未上映 A", today, 0, unavailable=True)]},
                "未上映 B": {today: [feature("未上映 B", today, 0, unavailable=True)]},
                "上映中 C": {
                    today: [
                        feature("上映中 C", today, 2),
                        feature("上映中 C", today, 0, unavailable=True),
                    ]
                },
            },
            "available_dates": [today],
            "movie_title": "未上映 A",
            "features": [feature("未上映 A", today, 0, unavailable=True)],
            "feature_count": 1,
        }

        result = sanitize_movie_availability(payload, today)

        self.assertEqual(result["movie_title"], "上映中 C")
        self.assertEqual([movie["title"] for movie in result["movies"]], ["上映中 C"])
        self.assertEqual(list(result["movie_features_by_date"]), ["上映中 C"])
        self.assertEqual(result["available_dates"], [today])
        self.assertEqual(len(result["features"]), 2)
        self.assertTrue(result["features"][1]["properties"]["showtime_unavailable"])

    def test_today_movie_is_ordered_before_future_only_presale_movie(self):
        today = "2026-09-01"
        future = "2026-09-05"
        payload = {
            "movies": [
                {"title": "預售片", "available_dates": [future]},
                {"title": "今日片", "available_dates": [today]},
            ],
            "movie_features_by_date": {
                "預售片": {future: [feature("預售片", future, 1)]},
                "今日片": {today: [feature("今日片", today, 1)]},
            },
            "movie_features": {},
            "available_dates": [future, today],
            "movie_title": "預售片",
            "features": [],
            "feature_count": 0,
        }

        result = sanitize_movie_availability(payload, today)

        self.assertEqual(list(result["movie_features_by_date"]), ["今日片", "預售片"])
        self.assertEqual(result["movie_title"], "今日片")
        self.assertEqual(result["available_dates"], [today, future])
        self.assertEqual(result["movies"][1]["available_dates"], [future])

    def test_no_real_showtimes_is_not_a_fake_available_movie(self):
        today = "2026-09-01"
        payload = {
            "movies": [{"title": "未上映", "available_dates": [today]}],
            "movie_features_by_date": {
                "未上映": {today: [feature("未上映", today, 0, unavailable=True)]}
            },
            "movie_features": {"未上映": [feature("未上映", today, 0, unavailable=True)]},
            "available_dates": [today],
            "movie_title": "未上映",
            "features": [feature("未上映", today, 0, unavailable=True)],
            "feature_count": 1,
        }

        result = sanitize_movie_availability(payload, today)

        self.assertEqual(result["movies"], [])
        self.assertEqual(result["movie_features_by_date"], {})
        self.assertEqual(result["movie_title"], None)
        self.assertEqual(result["features"], [])
        self.assertEqual(result["feature_count"], 0)
        self.assertEqual(result["available_dates"], [])
        self.assertEqual(result["empty_state"], "no_published_showtimes")


if __name__ == "__main__":
    unittest.main()
