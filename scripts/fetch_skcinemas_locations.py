from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from init_db import DEFAULT_DB_PATH, init_db


CHAIN_NAME = "新光影城"
OFFICIAL_URL = "https://www.skcinemas.com/"
FILMS_URL = "https://www.skcinemas.com/films"
DEFAULT_ENTRY_URL = "https://www.skcinemas.com/films?c=1001"


def infer_city(name: str) -> str | None:
    if "台北" in name:
        return "台北市"
    if "桃園" in name:
        return "桃園市"
    if "台中" in name:
        return "台中市"
    if "台南" in name:
        return "台南市"
    return None


def navigation_timeout_is_recoverable(error: Exception | None, captured: object) -> bool:
    return isinstance(error, PlaywrightTimeoutError) and bool(captured)


def wait_for_capture(page, captured: list[dict[str, object]], wait_ms: int) -> None:
    deadline = time.monotonic() + wait_ms / 1000
    while not captured and time.monotonic() < deadline:
        page.wait_for_timeout(200)


def fetch_locations(headless: bool = True, wait_ms: int = 8000) -> list[dict[str, object]]:
    captured: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, slow_mo=120 if not headless else 0)
        try:
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                locale="zh-TW",
                timezone_id="Asia/Taipei",
            )

            def on_response(response) -> None:
                if response.url.endswith("/api/VistaDataV2/GetAllForApp") and response.status == 200:
                    try:
                        payload = response.json()
                    except Exception:
                        return
                    if payload.get("result") is True and isinstance(payload.get("data"), list):
                        captured.extend(payload["data"])

            # Register before navigation: the API may finish before the document
            # reaches DOMContentLoaded on GitHub Actions runners.
            page.on("response", on_response)
            navigation_error: Exception | None = None
            try:
                page.goto(DEFAULT_ENTRY_URL, wait_until="commit", timeout=30_000)
            except PlaywrightTimeoutError as exc:
                navigation_error = exc
            wait_for_capture(page, captured, wait_ms)
            if navigation_error and not navigation_timeout_is_recoverable(navigation_error, captured):
                raise RuntimeError("新光據點頁導航逾時，且未取得 GetAllForApp API response") from navigation_error
            if not captured:
                raise RuntimeError("無法取得新光 GetAllForApp API response")
        finally:
            browser.close()

    locations: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in captured:
        cinema_id = str(item.get("CinemasID", "")).strip()
        name = str(item.get("CinemasName", "")).strip()
        if not cinema_id or not name or cinema_id in seen:
            continue
        seen.add(cinema_id)
        locations.append(
            {
                "source_location_code": cinema_id,
                "location_name": name,
                "city": infer_city(name),
                "latitude": float(item["Latitude"]) if item.get("Latitude") else None,
                "longitude": float(item["Longitude"]) if item.get("Longitude") else None,
                "location_url": f"{FILMS_URL}?c={cinema_id}",
                "source_url": DEFAULT_ENTRY_URL,
                "notes": "新光 films 頁瀏覽器攔截 GetAllForApp API 來源",
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
        (CHAIN_NAME, OFFICIAL_URL, FILMS_URL, "新光場館可由 films 頁 GetAllForApp API 取得"),
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
                    latitude,
                    longitude,
                    source_location_code,
                    location_url,
                    source_url,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chain_id, location_name) DO UPDATE SET
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
    parser = argparse.ArgumentParser(description="Fetch Shin Kong Cinemas locations.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--headed", action="store_true", help="Run browser visibly instead of headless.")
    parser.add_argument("--wait-ms", type=int, default=8000, help="Milliseconds to wait after page load.")
    args = parser.parse_args()

    locations = fetch_locations(headless=not args.headed, wait_ms=args.wait_ms)
    save_locations(locations, args.db)
    print(f"Fetched and saved Shin Kong locations: {len(locations)}")
    for location in locations:
        print(f"{location['source_location_code']} | {location['location_name']}")


if __name__ == "__main__":
    main()
