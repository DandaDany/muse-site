from __future__ import annotations

import argparse
import sqlite3
from collections import OrderedDict
from pathlib import Path

from playwright.sync_api import sync_playwright

from init_db import DEFAULT_DB_PATH, init_db


VIESHOW_URL = "https://www.vscinemas.com.tw/ShowTimes/"
VIESHOW_CHAIN = "威秀影城 / VIESHOW"
MUVIE_CHAIN = "MUVIE CINEMAS"


def has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def infer_city(location_name: str) -> str | None:
    if location_name.startswith(("台北", "MUVIE CINEMAS 台北")):
        return "台北市"
    if location_name.startswith(("板橋", "中和", "新店", "林口")):
        return "新北市"
    if location_name.startswith("桃園"):
        return "桃園市"
    if location_name.startswith("新竹"):
        return "新竹市"
    if location_name.startswith("頭份"):
        return "苗栗縣"
    if location_name.startswith(("台中", "MUVIE CINEMAS 台中")):
        return "台中市"
    if location_name.startswith("台南"):
        return "台南市"
    if location_name.startswith("高雄"):
        return "高雄市"
    if location_name.startswith("花蓮"):
        return "花蓮縣"
    return None


def chain_for(location_name: str) -> str:
    if location_name.startswith("MUVIE CINEMAS"):
        return MUVIE_CHAIN
    return VIESHOW_CHAIN


def fetch_locations(headless: bool = False, wait_ms: int = 8000) -> list[dict[str, str | None]]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, slow_mo=200 if not headless else 0)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            locale="zh-TW",
            timezone_id="Asia/Taipei",
        )
        page.goto(VIESHOW_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(wait_ms)
        options = page.locator("select option").evaluate_all(
            """
            options => options.map(option => ({
                value: (option.value || '').trim(),
                text: (option.textContent || '').trim()
            }))
            """
        )
        browser.close()

    by_code: OrderedDict[str, str] = OrderedDict()
    for option in options:
        code = option["value"]
        text = option["text"]
        if not code or not text or "請選擇" in text or "Please choose" in text:
            continue
        if not has_cjk(text):
            continue
        by_code.setdefault(code, text)

    return [
        {
            "source_location_code": code,
            "location_name": name,
            "chain_name": chain_for(name),
            "city": infer_city(name),
            "source_url": VIESHOW_URL,
            "location_url": VIESHOW_URL,
            "notes": "威秀場次頁下拉選單來源；實際地址與經緯度待補",
        }
        for code, name in by_code.items()
    ]


def upsert_chain(conn: sqlite3.Connection, chain_name: str) -> int:
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
            official_url = COALESCE(cinema_chains.official_url, excluded.official_url),
            crawl_url = excluded.crawl_url,
            all_locations_assumed_showing = 1,
            active = 1
        """,
        (chain_name, "https://www.vscinemas.com.tw/", VIESHOW_URL, "威秀 / MUVIE 場次查詢來源"),
    )
    row = conn.execute("SELECT id FROM cinema_chains WHERE chain_name = ?", (chain_name,)).fetchone()
    return int(row[0])


def save_locations(locations: list[dict[str, str | None]], db_path: Path) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        chain_ids: dict[str, int] = {}
        for location in locations:
            chain_name = str(location["chain_name"])
            if chain_name not in chain_ids:
                chain_ids[chain_name] = upsert_chain(conn, chain_name)
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
                    active = 1
                """,
                (
                    chain_ids[chain_name],
                    location["location_name"],
                    location["city"],
                    location["source_location_code"],
                    location["location_url"],
                    location["source_url"],
                    location["notes"],
                ),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch VIESHOW/MUVIE locations from the ShowTimes dropdown.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode.")
    parser.add_argument("--wait-ms", type=int, default=8000, help="Milliseconds to wait after page load.")
    args = parser.parse_args()

    locations = fetch_locations(headless=args.headless, wait_ms=args.wait_ms)
    save_locations(locations, args.db)
    print(f"Fetched and saved VIESHOW/MUVIE locations: {len(locations)}")
    for location in locations:
        print(f"{location['source_location_code']} | {location['location_name']}")


if __name__ == "__main__":
    main()
