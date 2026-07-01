from __future__ import annotations

import argparse
import re
import sqlite3
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlparse

from bs4 import BeautifulSoup

from init_db import DEFAULT_DB_PATH, init_db


CHAIN_NAME = "國賓影城"
OFFICIAL_URL = "https://www.ambassador.com.tw/"
THEATER_LIST_URL = "https://www.ambassador.com.tw/home/TheaterList"
KNOWN_SHOWTIME_LOCATION_ID = "453b2966-f7c2-44a9-b2eb-687493855d0e"


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


def normalize_showtime_url(location_id: str, show_date: str) -> str:
    dt = show_date.replace("-", "/")
    return f"https://www.ambassador.com.tw/home/Showtime?ID={quote(location_id)}&DT={dt}"


def known_showtime_url(show_date: str) -> str:
    return normalize_showtime_url(KNOWN_SHOWTIME_LOCATION_ID, show_date)


def split_city(address: str | None) -> str | None:
    if not address:
        return None
    for city in [
        "台北市",
        "新北市",
        "桃園市",
        "高雄市",
        "屏東縣",
        "金門縣",
    ]:
        if address.startswith(city):
            return city
    return None


def parse_theater_list(html: str, show_date: str) -> dict[str, dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    locations: dict[str, dict[str, str | None]] = {}
    for link in soup.find_all("a", href=True):
        href = urljoin(OFFICIAL_URL, link["href"])
        if "Showtime" not in href:
            continue
        location_id = (parse_qs(urlparse(href).query).get("ID") or [""])[0]
        if not location_id:
            continue

        text = " ".join(link.get_text(" ", strip=True).split())
        parts = re.split(r"\s+(?=(?:台北市|新北市|桃園市|高雄市|屏東縣|金門縣))", text, maxsplit=1)
        name = parts[0].strip()
        address = None
        if len(parts) > 1:
            address = re.sub(r"\s+0\d{1,3}[-\s]?\d{3,4}[-\s]?\d{3,4}.*$", "", parts[1]).strip()

        locations[location_id] = {
            "source_location_code": location_id,
            "location_name": name,
            "address": address,
            "city": split_city(address),
            "location_url": normalize_showtime_url(location_id, show_date),
            "source_url": THEATER_LIST_URL,
            "notes": "國賓 TheaterList 來源",
        }
    return locations


def parse_showtime_sidebar(html: str, show_date: str) -> dict[str, dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    locations: dict[str, dict[str, str | None]] = {}
    for link in soup.find_all("a", href=True):
        href = urljoin(OFFICIAL_URL, link["href"])
        if "Showtime" not in href:
            continue
        location_id = (parse_qs(urlparse(href).query).get("ID") or [""])[0]
        name = " ".join(link.get_text(" ", strip=True).split())
        if not location_id or not name or "2026" in name:
            continue
        locations.setdefault(
            location_id,
            {
                "source_location_code": location_id,
                "location_name": name,
                "address": None,
                "city": split_city(None),
                "location_url": normalize_showtime_url(location_id, show_date),
                "source_url": known_showtime_url(show_date),
                "notes": "國賓 Showtime 側欄來源",
            },
        )
    return locations


def merge_locations(*groups: dict[str, dict[str, str | None]]) -> list[dict[str, str | None]]:
    merged: dict[str, dict[str, str | None]] = {}
    for group in groups:
        for location_id, item in group.items():
            if location_id not in merged:
                merged[location_id] = item
                continue
            for key, value in item.items():
                if merged[location_id].get(key) in {None, ""} and value:
                    merged[location_id][key] = value
    return list(merged.values())


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
        (CHAIN_NAME, OFFICIAL_URL, THEATER_LIST_URL, "國賓場館入口可由 TheaterList 與 Showtime 側欄取得"),
    )
    row = conn.execute("SELECT id FROM cinema_chains WHERE chain_name = ?", (CHAIN_NAME,)).fetchone()
    return int(row[0])


def save_locations(locations: list[dict[str, str | None]], db_path: Path) -> None:
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
    parser = argparse.ArgumentParser(description="Fetch Ambassador cinema locations.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Show date for generated Showtime URLs.")
    parser.add_argument("--theater-list-html", type=Path, help="Optional local TheaterList HTML path.")
    parser.add_argument("--showtime-html", type=Path, help="Optional local Showtime HTML path.")
    args = parser.parse_args()

    theater_list_html = (
        args.theater_list_html.read_text(encoding="utf-8", errors="ignore")
        if args.theater_list_html
        else fetch_text(THEATER_LIST_URL)
    )
    showtime_html = (
        args.showtime_html.read_text(encoding="utf-8", errors="ignore")
        if args.showtime_html
        else fetch_text(known_showtime_url(args.date))
    )

    locations = merge_locations(
        parse_theater_list(theater_list_html, args.date),
        parse_showtime_sidebar(showtime_html, args.date),
    )
    save_locations(locations, args.db)
    print(f"Fetched and saved Ambassador locations: {len(locations)}")
    for location in locations:
        print(f"{location['source_location_code']} | {location['location_name']} | {location.get('address') or ''}")


if __name__ == "__main__":
    main()
