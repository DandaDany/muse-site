from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from typing import Iterable

from init_db import DEFAULT_DB_PATH, init_db


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = PROJECT_DIR / "data" / "input" / "cinema_sources.csv"


ALIASES = {
    "chain_name": ["chain_name", "cinema_chain", "cinema_name", "影城", "影城名稱", "影城品牌"],
    "official_url": ["official_url", "url", "link", "影城連結", "官方網址", "官方連結"],
    "crawl_url": ["crawl_url", "showtimes_url", "場次來源", "場次連結", "場次頁"],
    "booking_url": ["booking_url", "ticket_url", "訂票連結", "購票連結"],
    "all_locations_assumed_showing": [
        "all_locations_assumed_showing",
        "assume_all_locations",
        "全部據點上映",
        "所有據點上映",
    ],
    "notes": ["notes", "備註"],
    "location_name": ["location_name", "branch_name", "據點", "影城據點", "分店名稱"],
    "address": ["address", "地址"],
    "city": ["city", "縣市", "城市"],
    "district": ["district", "行政區", "區域"],
    "latitude": ["latitude", "lat", "緯度"],
    "longitude": ["longitude", "lng", "lon", "經度"],
    "source_location_code": ["source_location_code", "theater_code", "cinema_code", "影城代碼"],
    "location_url": ["location_url", "branch_url", "據點連結", "分店連結"],
}


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def parse_bool(value: str | None, default: bool = True) -> int:
    value = clean(value)
    if value is None:
        return int(default)
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "y", "上映", "是"}:
        return 1
    if normalized in {"0", "false", "no", "n", "否", "不是"}:
        return 0
    return int(default)


def parse_float(value: str | None) -> float | None:
    value = clean(value)
    if value is None:
        return None
    return float(value)


def value_for(row: dict[str, str], field_name: str) -> str | None:
    for alias in ALIASES[field_name]:
        if alias in row:
            return clean(row[alias])
    return None


def normalized_rows(csv_path: Path) -> Iterable[dict[str, object]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            chain_name = value_for(row, "chain_name")
            if not chain_name:
                raise ValueError(f"Missing chain_name on CSV row {row_number}.")

            yield {
                "chain_name": chain_name,
                "official_url": value_for(row, "official_url"),
                "crawl_url": value_for(row, "crawl_url"),
                "booking_url": value_for(row, "booking_url"),
                "all_locations_assumed_showing": parse_bool(
                    value_for(row, "all_locations_assumed_showing"),
                    default=True,
                ),
                "notes": value_for(row, "notes"),
                "location_name": value_for(row, "location_name"),
                "address": value_for(row, "address"),
                "city": value_for(row, "city"),
                "district": value_for(row, "district"),
                "latitude": parse_float(value_for(row, "latitude")),
                "longitude": parse_float(value_for(row, "longitude")),
                "source_location_code": value_for(row, "source_location_code"),
                "location_url": value_for(row, "location_url"),
            }


def upsert_chain(conn: sqlite3.Connection, item: dict[str, object]) -> int:
    conn.execute(
        """
        INSERT INTO cinema_chains (
            chain_name,
            official_url,
            crawl_url,
            booking_url,
            all_locations_assumed_showing,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(chain_name) DO UPDATE SET
            official_url = COALESCE(excluded.official_url, cinema_chains.official_url),
            crawl_url = COALESCE(excluded.crawl_url, cinema_chains.crawl_url),
            booking_url = COALESCE(excluded.booking_url, cinema_chains.booking_url),
            all_locations_assumed_showing = excluded.all_locations_assumed_showing,
            notes = COALESCE(excluded.notes, cinema_chains.notes),
            active = 1
        """,
        (
            item["chain_name"],
            item["official_url"],
            item["crawl_url"],
            item["booking_url"],
            item["all_locations_assumed_showing"],
            item["notes"],
        ),
    )
    row = conn.execute(
        "SELECT id FROM cinema_chains WHERE chain_name = ?",
        (item["chain_name"],),
    ).fetchone()
    return int(row[0])


def upsert_location(conn: sqlite3.Connection, chain_id: int, item: dict[str, object]) -> bool:
    location_name = item["location_name"]
    if not location_name:
        return False

    conn.execute(
        """
        INSERT INTO cinema_locations (
            chain_id,
            location_name,
            address,
            city,
            district,
            latitude,
            longitude,
            source_location_code,
            location_url,
            source_url,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chain_id, location_name) DO UPDATE SET
            address = COALESCE(excluded.address, cinema_locations.address),
            city = COALESCE(excluded.city, cinema_locations.city),
            district = COALESCE(excluded.district, cinema_locations.district),
            latitude = COALESCE(excluded.latitude, cinema_locations.latitude),
            longitude = COALESCE(excluded.longitude, cinema_locations.longitude),
            source_location_code = COALESCE(excluded.source_location_code, cinema_locations.source_location_code),
            location_url = COALESCE(excluded.location_url, cinema_locations.location_url),
            source_url = COALESCE(excluded.source_url, cinema_locations.source_url),
            notes = COALESCE(excluded.notes, cinema_locations.notes),
            active = 1
        """,
        (
            chain_id,
            location_name,
            item["address"],
            item["city"],
            item["district"],
            item["latitude"],
            item["longitude"],
            item["source_location_code"],
            item["location_url"],
            item["crawl_url"] or item["official_url"],
            item["notes"],
        ),
    )
    return True


def import_cinema_sources(csv_path: Path, db_path: Path, replace: bool = False) -> tuple[int, int]:
    init_db(db_path)
    chains_seen: set[int] = set()
    location_count = 0

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        if replace:
            conn.execute("DELETE FROM cinema_chains")
        for item in normalized_rows(csv_path):
            chain_id = upsert_chain(conn, item)
            chains_seen.add(chain_id)
            if upsert_location(conn, chain_id, item):
                location_count += 1

    return len(chains_seen), location_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Import cinema chains and optional locations.")
    parser.add_argument("csv", nargs="?", type=Path, default=DEFAULT_CSV_PATH, help="Input CSV path.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace existing cinema chains and locations before importing.",
    )
    args = parser.parse_args()

    chain_count, location_count = import_cinema_sources(args.csv, args.db, replace=args.replace)
    print(f"Imported or updated cinema chains: {chain_count}")
    print(f"Imported or updated cinema locations: {location_count}")
    print(f"Database: {args.db}")


if __name__ == "__main__":
    main()
