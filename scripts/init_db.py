from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_DIR / "data" / "movie_map.sqlite"
SCHEMA_PATH = PROJECT_DIR / "sql" / "schema.sql"


MIGRATIONS = {
    "cinema_locations": {
        "source_location_code": "ALTER TABLE cinema_locations ADD COLUMN source_location_code TEXT",
        "notes": "ALTER TABLE cinema_locations ADD COLUMN notes TEXT",
    },
}


def ensure_migrations(conn: sqlite3.Connection) -> None:
    for table_name, columns in MIGRATIONS.items():
        existing_columns = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        for column_name, sql in columns.items():
            if column_name not in existing_columns:
                conn.execute(sql)


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(schema_sql)
        ensure_migrations(conn)
    finally:
        conn.close()


def list_tables(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()
    return [row[0] for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the movie map SQLite database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    args = parser.parse_args()

    init_db(args.db)
    print(f"Database initialized: {args.db}")
    print("Objects:")
    for table_name in list_tables(args.db):
        print(f"- {table_name}")


if __name__ == "__main__":
    main()
