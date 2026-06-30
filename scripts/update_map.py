from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MOVIE_LIST = PROJECT_DIR / "電影清單.txt"


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch showtimes and export the local web map GeoJSON.")
    parser.add_argument("--movie-list", type=Path, default=DEFAULT_MOVIE_LIST, help="Text file containing numbered movie titles.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Show date, defaults to today.")
    args = parser.parse_args()
    movie_list_path = args.movie_list if args.movie_list.is_absolute() else PROJECT_DIR / args.movie_list
    movie_titles = read_movie_titles(movie_list_path)
    if not movie_titles:
        raise SystemExit(f"No movie titles found in {movie_list_path}")

    print("========================================")
    print("Kapok movie map update")
    print("========================================")
    print(f"Movie list: {movie_list_path}")
    print(f"Date      : {args.date}")
    print("Movies:")
    for index, movie_title in enumerate(movie_titles, start=1):
        print(f"  {index}. {movie_title}")
    print()

    for movie_title in movie_titles:
        print(f"Fetching showtimes: {movie_title}")
        run_step(["scripts/fetch_movie_showtimes.py", movie_title, "--date", args.date])
        print()

    print()
    print("Exporting web/data/locations.geojson ...")
    export_args = ["scripts/export_geojson.py", "--date", args.date]
    for movie_title in movie_titles:
        export_args.extend(["--movie-title", movie_title])
    run_step(export_args)

    print()
    print("[DONE] Map data updated.")
    print("Output: web/data/locations.geojson")


if __name__ == "__main__":
    main()
