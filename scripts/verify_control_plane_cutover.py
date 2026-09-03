"""Post-crawl cutover gate for the GitHub-only control plane.

Runs after a full crawl with backend environment variables cleared. It verifies that
movie selection, cinema code persistence, crawler execution, and final GeoJSON are
internally consistent with the canonical GitHub files.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import control_data  # noqa: E402
from init_db import DEFAULT_DB_PATH  # noqa: E402
from update_map import read_movie_titles  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parents[1]
MOVIE_LIST = PROJECT_DIR / "電影清單.txt"
GEOJSON = PROJECT_DIR / "web" / "data" / "locations.geojson"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def _runtime_codes(db_path: Path) -> dict[tuple[str, str], str]:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT cc.chain_name, cl.location_name, cl.source_location_code
            FROM cinema_locations cl
            JOIN cinema_chains cc ON cc.id = cl.chain_id
            WHERE cl.source_location_code IS NOT NULL
              AND TRIM(cl.source_location_code) <> ''
            """
        ).fetchall()
    return {(chain, location): code.strip() for chain, location, code in rows}


def _canonical_codes(master: dict) -> dict[tuple[str, str], str]:
    chain_names = {chain["id"]: chain["chain_name"] for chain in master["chains"]}
    result = {}
    for loc in master["locations"]:
        code = (loc.get("source_location_code") or "").strip()
        if code:
            result[(chain_names[loc["chain_id"]], loc["location_name"])] = code
    return result


def _crawl_status(db_path: Path, show_date: str) -> tuple[int, int, int]:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT status FROM crawl_runs WHERE show_date = ?",
            (show_date,),
        ).fetchall()
    statuses = [row[0] for row in rows]
    success = sum(1 for status in statuses if status == "success")
    failed = sum(1 for status in statuses if status in ("failed", "partial"))
    return len(statuses), success, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify GitHub-only production cutover.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--geojson", type=Path, default=GEOJSON)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    tracked = control_data.load_tracked_movies()
    cinemas = control_data.load_cinema_master()

    expected_movies = [
        movie["title"]
        for movie in control_data.eligible_movies(
            tracked,
            datetime.now(TAIPEI_TZ).date(),
        )
    ]
    actual_movies = read_movie_titles(MOVIE_LIST)
    if actual_movies != expected_movies:
        raise RuntimeError(
            f"movie-list cutover parity failed: expected={expected_movies!r} actual={actual_movies!r}"
        )

    runtime_codes = _runtime_codes(args.db)
    canonical_codes = _canonical_codes(cinemas)
    code_mismatches = {
        key: {"runtime": code, "canonical": canonical_codes.get(key)}
        for key, code in runtime_codes.items()
        if canonical_codes.get(key) != code
    }
    if code_mismatches:
        raise RuntimeError(
            "dynamic code persistence failed: "
            + json.dumps(code_mismatches, ensure_ascii=False, indent=2)
        )

    total_runs, success_runs, failed_runs = _crawl_status(args.db, args.date)
    if expected_movies and (total_runs == 0 or success_runs == 0):
        raise RuntimeError(
            f"production crawl gate failed: runs={total_runs}, success={success_runs}, failed={failed_runs}"
        )

    payload = json.loads(args.geojson.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise RuntimeError("GeoJSON output is not a FeatureCollection")
    if payload.get("show_date") != args.date:
        raise RuntimeError(
            f"GeoJSON show_date mismatch: {payload.get('show_date')} != {args.date}"
        )

    expected_set = set(expected_movies)
    published_titles = {
        item.get("title")
        for item in payload.get("movies", [])
        if isinstance(item, dict) and item.get("title")
    }
    by_date = payload.get("movie_features_by_date") or {}
    if isinstance(by_date, dict):
        published_titles.update(by_date.keys())
    unexpected = published_titles - expected_set
    if unexpected:
        raise RuntimeError(f"GeoJSON contains untracked movie titles: {sorted(unexpected)}")

    if not expected_movies:
        if payload.get("features"):
            raise RuntimeError("0-movie cutover must not publish map features")

    report = {
        "status": "PASS",
        "generated_at": datetime.now(TAIPEI_TZ).isoformat(),
        "show_date": args.date,
        "gates": {
            "movie_list_from_git": True,
            "dynamic_codes_persisted": True,
            "production_crawl_executed": True,
            "geojson_contract_valid": True,
        },
        "counts": {
            "runtime_movies": len(expected_movies),
            "crawl_runs": total_runs,
            "successful_crawl_runs": success_runs,
            "failed_or_partial_crawl_runs": failed_runs,
            "runtime_codes": len(runtime_codes),
            "published_movies": len(published_titles),
        },
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
