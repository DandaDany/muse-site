from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from init_db import DEFAULT_DB_PATH, init_db


TABLES = [
    "cinema_chains",
    "cinema_locations",
    "movies",
    "movie_targets",
    "showtimes",
    "crawl_runs",
    "kml_exports",
]


def count_rows(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
    return int(row[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="Print database row counts.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    args = parser.parse_args()

    init_db(args.db)
    with sqlite3.connect(args.db) as conn:
        print(f"Database: {args.db}")
        for table_name in TABLES:
            print(f"{table_name}: {count_rows(conn, table_name)}")


if __name__ == "__main__":
    main()
