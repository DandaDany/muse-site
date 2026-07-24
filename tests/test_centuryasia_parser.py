from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_DIR / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS_DIR))

import fetch_movie_showtimes as showtimes  # noqa: E402


SHOW_DATE = "2026-07-24"
TOY_STORY_ALIASES = ["玩具總動員5", "Toy Story 5"]
ODYSSEY_ALIASES = ["奧德賽", "The Odyssey"]


def parse_fixture(name: str, aliases: list[str], show_date: str = SHOW_DATE):
    html_text = (FIXTURES_DIR / name).read_text(encoding="utf-8")
    return showtimes.parse_centuryasia(
        html_text,
        aliases=aliases,
        show_date=show_date,
        location_id=1,
        source_url="https://example.test/century",
    )


class CenturyasiaLegacyTemplateTests(unittest.TestCase):
    """舊版 ticket_online.aspx 模板（西門今日店）。"""

    def test_toy_story_showtimes_are_extracted(self):
        records = parse_fixture("centuryasia_legacy_ximen.html", TOY_STORY_ALIASES)
        times = sorted(r.start_time for r in records)
        self.assertEqual(times, ["12:35", "14:40", "16:45", "21:15"])

    def test_language_and_booking_url_are_captured(self):
        records = parse_fixture("centuryasia_legacy_ximen.html", TOY_STORY_ALIASES)
        by_time = {r.start_time: r for r in records}
        self.assertEqual(by_time["12:35"].language, "國語")
        self.assertEqual(by_time["14:40"].language, "英語")
        self.assertTrue(by_time["12:35"].booking_url.startswith("https://ticket.centuryasia.com.tw/"))

    def test_past_session_without_onclick_still_counts(self):
        # 奧德賽 5廳 11:30 沒有 onclick（已過場次），仍應列入當日場次。
        records = parse_fixture("centuryasia_legacy_ximen.html", ODYSSEY_ALIASES)
        self.assertIn("11:30", {r.start_time for r in records})

    def test_only_matching_movie_is_returned(self):
        records = parse_fixture("centuryasia_legacy_ximen.html", TOY_STORY_ALIASES)
        self.assertTrue(all("再生家族" not in (r.raw_text or "") for r in records))


class CenturyasiaShowtimeUrlTests(unittest.TestCase):
    """各館場次頁對照：以館名/代碼/既有網址關鍵字命中，歇業館回 None。"""

    def _row(self, name="", code="", url=""):
        return {"location_name": name, "source_location_code": code, "location_url": url}

    def test_nangang_uses_new_book_template(self):
        url = showtimes.centuryasia_showtime_url(self._row(name="喜樂時代影城南港店"))
        self.assertEqual(url, "https://www.centuryasia.com.tw/book.html?sid=Nangang&ver=0fKKApRlrx8=")

    def test_ximen_uses_legacy_template(self):
        url = showtimes.centuryasia_showtime_url(self._row(name="喜樂時代影城西門今日店"))
        self.assertEqual(url, "https://ximen.centuryasia.com.tw/ticket_online.aspx?page=0")

    def test_kaohsiung_matches_via_ksml_subdomain(self):
        # 後台代碼是 kaohsiung，但子網域是 ksml，兩者都應命中。
        by_name = showtimes.centuryasia_showtime_url(self._row(name="喜樂時代影城高雄總圖店"))
        by_url = showtimes.centuryasia_showtime_url(
            self._row(url="https://ksml.centuryasia.com.tw/index.aspx")
        )
        self.assertEqual(by_name, "https://ksml.centuryasia.com.tw/ticket_online.aspx?page=0")
        self.assertEqual(by_url, by_name)

    def test_closed_taoyuan_is_skipped(self):
        url = showtimes.centuryasia_showtime_url(self._row(name="喜樂時代影城桃園A19店", code="taoyuan"))
        self.assertIsNone(url)

    def test_override_ignores_stale_index_url(self):
        # 後台存的是舊入口頁，仍應被館名關鍵字導向正確場次頁。
        url = showtimes.centuryasia_showtime_url(
            self._row(name="喜樂時代影城永和店", url="https://ticket.centuryasia.com.tw/beyond/index.aspx")
        )
        self.assertEqual(url, "https://beyond.centuryasia.com.tw/ticket_online.aspx?page=0")


class CenturyasiaNewTemplateTests(unittest.TestCase):
    """新版 book.html 週表模板（南港店）。"""

    def test_odyssey_active_date_showtimes_are_extracted(self):
        records = parse_fixture("centuryasia_book_nangang.html", ODYSSEY_ALIASES)
        times = sorted(r.start_time for r in records)
        self.assertEqual(
            times,
            [
                "11:00", "11:40", "12:20", "13:00", "13:35", "14:10", "14:55",
                "15:35", "16:15", "16:50", "17:30", "18:10", "18:50", "19:30",
                "20:05", "20:45", "21:25", "22:05",
            ],
        )

    def test_hall_and_format_split(self):
        records = parse_fixture("centuryasia_book_nangang.html", ODYSSEY_ALIASES)
        by_time = {r.start_time: r for r in records}
        self.assertEqual(by_time["12:20"].auditorium, "1廳")
        self.assertEqual(by_time["12:20"].format, "2D英語")
        self.assertEqual(by_time["12:20"].language, "英語")

    def test_movie_showing_on_other_date_is_excluded(self):
        # 蜘蛛人：重生日的 active 日期是 07.29，非 07/24，應被日期過濾排除。
        records = parse_fixture("centuryasia_book_nangang.html", ["蜘蛛人", "Spider-Man"])
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
