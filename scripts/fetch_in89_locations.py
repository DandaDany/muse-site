from __future__ import annotations

import argparse
import sqlite3
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from init_db import DEFAULT_DB_PATH, init_db


CHAIN_NAME = "in89 豪華影城"
OFFICIAL_URL = "https://www.in89cinemax.com/"


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


def infer_city(name: str) -> str | None:
    if name.startswith("台北"):
        return "台北市"
    if name.startswith("桃園"):
        return "桃園市"
    if name.startswith("台中"):
        return "台中市"
    if name.startswith("嘉義"):
        return "嘉義市"
    if name.startswith("高雄"):
        return "高雄市"
    if name.startswith("澎湖"):
        return "澎湖縣"
    return None


def normalize_name(name: str) -> str:
    return name.replace("_", " ").strip()


def extract_locations(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    locations: list[dict[str, object]] = []
    for option in soup.select("select#dropTheater option"):
        theater_id = (option.get("value") or "").strip()
        raw_name = option.get_text(strip=True)
        if not theater_id or not raw_name or "請選擇" in raw_name:
            continue
        name = normalize_name(raw_name)
        locations.append(
            {
                "source_location_code": theater_id,
                "location_name": name,
                "city": infer_city(name),
                "location_url": urljoin(OFFICIAL_URL, f"film_list.aspx?TheaterId={theater_id}"),
                "source_url": OFFICIAL_URL,
                "notes": "in89 首頁影城下拉選單來源；地址待由影城介紹或地理編碼補齊",
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
            active = 1
        """,
        (CHAIN_NAME, OFFICIAL_URL, OFFICIAL_URL, "in89 場館 ID 可由首頁下拉選單取得"),
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
                    city,
                    source_location_code,
                    location_url,
                    source_url,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chain_id, location_name) DO UPDATE SET
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
                    location["city"],
                    location["source_location_code"],
                    location["location_url"],
                    location["source_url"],
                    location["notes"],
                ),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch in89 locations from homepage dropdown.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--input-html", type=Path, help="Optional local homepage HTML path.")
    args = parser.parse_args()

    html = args.input_html.read_text(encoding="utf-8", errors="ignore") if args.input_html else fetch_text(OFFICIAL_URL)
    locations = extract_locations(html)
    save_locations(locations, args.db)
    print(f"Fetched and saved in89 locations: {len(locations)}")
    for location in locations:
        print(f"{location['source_location_code']} | {location['location_name']}")


if __name__ == "__main__":
    main()
