"""Verify version-controlled location codes after a cinema-master rebuild."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from import_cinema_sources import DEFAULT_DB_PATH, normalized_rows


def verify_codes(csv_path: Path, db_path: Path, chain_name: str) -> int:
    expected = [
        row
        for row in normalized_rows(csv_path)
        if row["chain_name"] == chain_name and row["source_location_code"]
    ]
    if not expected:
        raise ValueError(f"No version-controlled codes found for {chain_name}.")

    failures: list[str] = []
    with sqlite3.connect(db_path) as conn:
        for item in expected:
            row = conn.execute(
                """
                SELECT cl.active, cl.source_location_code
                FROM cinema_locations cl
                JOIN cinema_chains cc ON cc.id = cl.chain_id
                WHERE cc.chain_name = ? AND cl.location_name = ?
                """,
                (chain_name, item["location_name"]),
            ).fetchone()
            if not row:
                failures.append(f"missing {item['location_name']}")
            elif not row[0]:
                failures.append(f"inactive {item['location_name']}")
            elif row[1] != item["source_location_code"]:
                failures.append(
                    f"{item['location_name']} code={row[1]!r}, expected={item['source_location_code']!r}"
                )
    conn.close()
    if failures:
        raise RuntimeError(f"{chain_name} code verification failed: " + "; ".join(failures))
    print(f"Verified {chain_name} active locations with versioned codes: {len(expected)}")
    return len(expected)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a chain's version-controlled cinema codes.")
    parser.add_argument("--csv", type=Path, default=PROJECT_DIR / "data" / "input" / "cinema_codes.csv")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--chain", required=True)
    args = parser.parse_args()
    verify_codes(args.csv, args.db, args.chain)


PROJECT_DIR = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    main()
