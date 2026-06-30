from __future__ import annotations

import argparse
import json
import sqlite3
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from init_db import DEFAULT_DB_PATH, init_db


CHAIN_NAME = "秀泰影城"
OFFICIAL_URL = "https://www.showtimes.com.tw/"
BOOTSTRAP_URL = "https://capi.showtimes.com.tw/4/app/bootstrap"


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Origin": OFFICIAL_URL.rstrip("/"),
            "Referer": OFFICIAL_URL,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def split_city(address: str | None, name: str) -> str | None:
    if not address:
        if name.startswith("台東"):
            return "台東縣"
        return None
    for city in [
        "台北市",
        "新北市",
        "桃園市",
        "台中市",
        "台南市",
        "高雄市",
        "基隆市",
        "新竹市",
        "嘉義市",
        "雲林縣",
        "花蓮縣",
        "台東縣",
    ]:
        if address.startswith(city):
            return city
    if address.startswith("台東市"):
        return "台東縣"
    return None


def parse_lat_lng(value: str | None) -> tuple[float | None, float | None]:
    if not value or "," not in value:
        return None, None
    lat_text, lng_text = value.split(",", 1)
    return float(lat_text.strip()), float(lng_text.strip())


def ticketing_url(cinema_id: int, show_date: str) -> str:
    query = urlencode({"cid": cinema_id, "date": show_date, "category": "popular"})
    return f"https://www.showtimes.com.tw/ticketing?{query}"


def extract_locations(payload: dict, show_date: str) -> list[dict[str, object]]:
    locations: list[dict[str, object]] = []
    for corporation in payload.get("corporations", []):
        cinema_id = int(corporation["id"])
        name = corporation.get("name")
        address = corporation.get("address")
        meta = corporation.get("meta") or {}
        latitude, longitude = parse_lat_lng(meta.get("latLng"))
        locations.append(
            {
                "source_location_code": str(cinema_id),
                "location_name": name,
                "address": address,
                "city": split_city(address, name or ""),
                "latitude": latitude,
                "longitude": longitude,
                "location_url": ticketing_url(cinema_id, show_date),
                "source_url": BOOTSTRAP_URL,
                "notes": "秀泰 bootstrap API corporations 來源",
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
        (CHAIN_NAME, OFFICIAL_URL, BOOTSTRAP_URL, "秀泰場館與場次資料可由 capi.showtimes.com.tw API 取得"),
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
                    latitude,
                    longitude,
                    source_location_code,
                    location_url,
                    source_url,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chain_id, location_name) DO UPDATE SET
                    address = COALESCE(excluded.address, cinema_locations.address),
                    city = COALESCE(excluded.city, cinema_locations.city),
                    latitude = COALESCE(excluded.latitude, cinema_locations.latitude),
                    longitude = COALESCE(excluded.longitude, cinema_locations.longitude),
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
                    location["latitude"],
                    location["longitude"],
                    location["source_location_code"],
                    location["location_url"],
                    location["source_url"],
                    location["notes"],
                ),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch ShowTimes cinema locations from bootstrap API.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Show date for generated ticketing URLs.")
    parser.add_argument(
        "--input-json",
        type=Path,
        help="Optional local bootstrap JSON path for offline parsing.",
    )
    args = parser.parse_args()

    if args.input_json:
        data = json.loads(args.input_json.read_text(encoding="utf-8"))
    else:
        data = fetch_json(BOOTSTRAP_URL)

    locations = extract_locations(data["payload"], args.date)
    save_locations(locations, args.db)
    print(f"Fetched and saved ShowTimes locations: {len(locations)}")
    for location in locations:
        print(f"{location['source_location_code']} | {location['location_name']}")


if __name__ == "__main__":
    main()
