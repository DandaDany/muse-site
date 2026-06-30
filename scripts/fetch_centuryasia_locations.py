from __future__ import annotations

import argparse
import sqlite3
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from init_db import DEFAULT_DB_PATH, init_db


CHAIN_NAME = "喜樂時代影城"
OFFICIAL_URL = "https://www.centuryasia.com.tw/"
TICKETING_URL = "https://ticket.centuryasia.com.tw/"

SLUG_METADATA = {
    "ximen": {
        "name": "喜樂時代影城西門今日店",
        "city": "台北市",
        "address": "台北市萬華區峨眉街52號",
    },
    "nangang": {
        "name": "喜樂時代影城南港店",
        "city": "台北市",
        "address": "台北市南港區忠孝東路七段299號",
    },
    "beyond": {
        "name": "喜樂時代影城永和店",
        "city": "新北市",
        "address": "新北市永和區中山路一段238號",
    },
    "taoyuan": {
        "name": "喜樂時代影城桃園A19店",
        "city": "桃園市",
        "address": "桃園市中壢區高鐵南路二段352號",
    },
    "kaohsiung": {
        "name": "喜樂時代影城高雄總圖店",
        "city": "高雄市",
        "address": "高雄市前鎮區林森四路189號",
    },
}


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def slug_from_url(url: str) -> str | None:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if not parts:
        return None
    return parts[0].lower()


def extract_locations(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    locations: list[dict[str, object]] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        href = link["href"].replace('"', "").strip()
        if "ticket.centuryasia.com.tw" not in href or "index.aspx" not in href:
            continue
        slug = slug_from_url(href)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        metadata = SLUG_METADATA.get(slug, {})
        locations.append(
            {
                "source_location_code": slug,
                "location_name": metadata.get("name") or f"喜樂時代影城 {slug}",
                "address": metadata.get("address"),
                "city": metadata.get("city"),
                "location_url": href,
                "source_url": TICKETING_URL,
                "notes": "喜樂時代票務首頁連結來源；場次需進入各館 movie_timetable.aspx 解析。",
            }
        )
    return locations


def upsert_chain(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        INSERT INTO cinema_chains (
            chain_name,
            official_url,
            crawl_url,
            all_locations_assumed_showing,
            notes
        )
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(chain_name) DO UPDATE SET
            official_url = excluded.official_url,
            crawl_url = excluded.crawl_url,
            all_locations_assumed_showing = 1,
            notes = excluded.notes,
            active = 1
        """,
        (CHAIN_NAME, OFFICIAL_URL, TICKETING_URL, "喜樂時代場館入口可由 ticket 票務首頁取得。"),
    )
    row = conn.execute("SELECT id FROM cinema_chains WHERE chain_name = ?", (CHAIN_NAME,)).fetchone()
    return int(row[0])


def save_locations(locations: list[dict[str, object]], db_path: Path) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        chain_id = upsert_chain(conn)
        for location in locations:
            conn.execute(
                """
                INSERT INTO cinema_locations (
                    chain_id,
                    location_name,
                    address,
                    city,
                    source_location_code,
                    location_url,
                    source_url,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chain_id, location_name) DO UPDATE SET
                    address = COALESCE(excluded.address, cinema_locations.address),
                    city = COALESCE(excluded.city, cinema_locations.city),
                    source_location_code = excluded.source_location_code,
                    location_url = excluded.location_url,
                    source_url = excluded.source_url,
                    notes = excluded.notes,
                    active = 1
                """,
                (
                    chain_id,
                    location["location_name"],
                    location["address"],
                    location["city"],
                    location["source_location_code"],
                    location["location_url"],
                    location["source_url"],
                    location["notes"],
                ),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Century Asia cinema locations from ticketing homepage.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--input-html", type=Path, help="Optional local ticketing homepage HTML path.")
    args = parser.parse_args()

    html = args.input_html.read_text(encoding="utf-8", errors="ignore") if args.input_html else fetch_text(TICKETING_URL)
    locations = extract_locations(html)
    save_locations(locations, args.db)
    print(f"Fetched and saved Century Asia locations: {len(locations)}")
    for location in locations:
        print(f"{location['source_location_code']} | {location['location_name']}")


if __name__ == "__main__":
    main()
