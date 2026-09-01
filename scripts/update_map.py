from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from map_availability import sanitize_geojson_file
from movie_title_matching import aliases_for_titles
from showtime_availability import MAX_SOURCE_LOOKAHEAD_DAYS


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MOVIE_LIST = PROJECT_DIR / "電影清單.txt"
DEFAULT_OUTPUT = PROJECT_DIR / "web" / "data" / "locations.geojson"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def read_movie_titles(path: Path) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        title = re.sub(r"^\s*\d+\s*[.)、]\s*", "", raw_line).strip()
        if not title or title.startswith("#"):
            continue
        if title not in seen:
            titles.append(title)
            seen.add(title)
    return titles


def run_step(args: list[str]) -> None:
    subprocess.run([sys.executable, *args], cwd=PROJECT_DIR, check=True)


def build_fetch_args(movie_title: str, show_dates: list[str], aliases: list[str]) -> list[str]:
    """Build the crawler command with backend aliases and all requested dates."""
    args = ["scripts/fetch_movie_showtimes_runner.py", movie_title]
    for alias in aliases:
        args.extend(["--alias", alias])
    for show_date in show_dates:
        args.extend(["--date", show_date])
    return args


def write_empty_movie_map(show_date: str, output: Path = DEFAULT_OUTPUT) -> None:
    """輸出合法的空電影地圖狀態，不沿用昨天的電影或退回影城主檔模式。"""
    payload = {
        "type": "FeatureCollection",
        "name": "木棉花電影全台上映地圖",
        "generated_at": date.today().isoformat(),
        "updated_at": datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
        "movie_title": None,
        "show_date": show_date,
        "movies": [],
        "movie_features": {},
        "movie_features_by_date": {},
        "available_dates": [],
        "feature_count": 0,
        "features": [],
        "empty_state": "no_movies_today",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"GeoJSON exported: {output}")
    print("Movies: 0 (today has no tracked theatrical movies)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch showtimes and export the local web map GeoJSON.")
    parser.add_argument("--movie-list", type=Path, default=DEFAULT_MOVIE_LIST, help="Text file containing numbered movie titles.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Show date, defaults to today.")
    args = parser.parse_args()
    movie_list_path = args.movie_list if args.movie_list.is_absolute() else PROJECT_DIR / args.movie_list
    movie_titles = read_movie_titles(movie_list_path)

    print("========================================")
    print("Kapok movie map update")
    print("========================================")
    print(f"Movie list: {movie_list_path}")

    if not movie_titles:
        print("Movies    : 0 — export empty movie state; no cinema crawler will run.")
        write_empty_movie_map(args.date)
        print()
        print("[DONE] Map data updated.")
        print("Output: web/data/locations.geojson")
        return

    start_date = date.fromisoformat(args.date)
    show_dates = [
        (start_date + timedelta(days=offset)).isoformat()
        for offset in range(MAX_SOURCE_LOOKAHEAD_DAYS + 1)
    ]
    alias_map = aliases_for_titles(movie_titles)
    print(f"Dates     : {show_dates[0]} through {show_dates[-1]}")
    print("Movies:")
    for index, movie_title in enumerate(movie_titles, start=1):
        alias_count = len(alias_map.get(movie_title, []))
        print(f"  {index}. {movie_title} (aliases={alias_count})")
    print()

    for movie_title in movie_titles:
        print(f"Fetching showtimes: {movie_title}")
        fetch_args = build_fetch_args(movie_title, show_dates, alias_map.get(movie_title, []))
        run_step(fetch_args)
        print()

    print()
    print("Exporting web/data/locations.geojson ...")
    export_args = ["scripts/export_geojson.py", "--date", args.date]
    for show_date in show_dates[1:]:
        export_args.extend(["--additional-date", show_date])
    for movie_title in movie_titles:
        export_args.extend(["--movie-title", movie_title])
    run_step(export_args)

    # A 0-showtime fallback pin is useful as a source-unavailable notice, but it
    # must never make an upcoming movie/date selectable or become the default.
    sanitize_geojson_file(DEFAULT_OUTPUT, args.date)

    print()
    print("[DONE] Map data updated.")
    print("Output: web/data/locations.geojson")


if __name__ == "__main__":
    main()
