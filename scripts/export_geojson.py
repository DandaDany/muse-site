from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path

from init_db import DEFAULT_DB_PATH, init_db


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_DIR / "web" / "data" / "locations.geojson"


def fetch_location_features(conn: sqlite3.Connection) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT
            location_id,
            chain_name,
            location_name,
            map_name,
            address,
            city,
            latitude,
            longitude,
            location_url,
            official_url,
            crawl_url
        FROM v_location_map_points
        WHERE latitude IS NOT NULL
          AND longitude IS NOT NULL
        ORDER BY chain_name, location_name
        """
    ).fetchall()

    features: list[dict[str, object]] = []
    for row in rows:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [row["longitude"], row["latitude"]],
                },
                "properties": {
                    "location_id": row["location_id"],
                    "chain_name": row["chain_name"],
                    "location_name": row["location_name"],
                    "map_name": row["map_name"],
                    "address": row["address"],
                    "city": row["city"],
                    "location_url": row["location_url"],
                    "official_url": row["official_url"],
                    "crawl_url": row["crawl_url"],
                },
            }
        )
    return features


def fetch_showtime_features(conn: sqlite3.Connection, movie_title: str, show_date: str) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT
            s.id AS showtime_id,
            m.title AS movie_title,
            cl.id AS location_id,
            cc.chain_name,
            cl.location_name,
            COALESCE(cl.display_name, cc.chain_name || ' ' || cl.location_name) AS map_name,
            cl.address,
            cl.city,
            cl.latitude,
            cl.longitude,
            cl.location_url,
            cc.official_url,
            s.show_date,
            s.start_time,
            s.auditorium,
            s.format,
            s.language,
            s.booking_url,
            s.source_url
        FROM showtimes s
        JOIN movies m ON m.id = s.movie_id
        JOIN cinema_locations cl ON cl.id = s.location_id
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE m.title = ?
          AND s.show_date = ?
          AND cl.latitude IS NOT NULL
          AND cl.longitude IS NOT NULL
          AND m.active = 1
          AND cl.active = 1
          AND cc.active = 1
        ORDER BY cc.chain_name, cl.location_name, s.start_time
        """,
        (movie_title, show_date),
    ).fetchall()

    grouped: dict[tuple[object, ...], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                row["chain_name"],
                row["location_id"],
                row["location_name"],
                row["map_name"],
                row["address"],
                row["city"],
                row["latitude"],
                row["longitude"],
            )
        ].append(row)

    features: list[dict[str, object]] = []
    for group_rows in grouped.values():
        first = group_rows[0]
        showtimes = []
        for row in group_rows:
            labels = [row["format"], row["auditorium"]]
            label = " / ".join(str(value) for value in labels if value)
            showtimes.append(
                {
                    "time": row["start_time"],
                    "format": row["format"],
                    "language": row["language"],
                    "auditorium": row["auditorium"],
                    "booking_url": row["booking_url"],
                    "label": f"{row['start_time']} {label}".strip(),
                }
            )
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [first["longitude"], first["latitude"]],
                },
                "properties": {
                    "location_id": first["location_id"],
                    "chain_name": first["chain_name"],
                    "location_name": first["location_name"],
                    "map_name": first["map_name"],
                    "address": first["address"],
                    "city": first["city"],
                    "location_url": first["booking_url"] or first["location_url"] or first["official_url"] or first["source_url"],
                    "official_url": first["official_url"],
                    "crawl_url": first["source_url"],
                    "movie_title": first["movie_title"],
                    "show_date": first["show_date"],
                    "showtime_count": len(showtimes),
                    "showtimes": showtimes,
                    "start_times": ", ".join(item["time"] for item in showtimes),
                },
            }
        )
    return features


def movie_payload(conn: sqlite3.Connection, movie_title: str, show_date: str) -> dict[str, object]:
    features = fetch_showtime_features(conn, movie_title, show_date)
    return {
        "title": movie_title,
        "show_date": show_date,
        "feature_count": len(features),
        "features": features,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export cinema locations or movie showtimes to GeoJSON for the local web map.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output GeoJSON path.")
    parser.add_argument("--movie-title", action="append", default=[], help="Export showtimes for this movie. Can be repeated.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Show date for showtime export.")
    args = parser.parse_args()

    init_db(args.db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db) as conn:
        conn.row_factory = sqlite3.Row
        movie_titles = [title for title in args.movie_title if title]
        if movie_titles:
            movie_payloads = [movie_payload(conn, movie_title, args.date) for movie_title in movie_titles]
            first_movie = movie_payloads[0]
            features = first_movie["features"]
            collection_name = "木棉花電影全台上映地圖"
            movies = [
                {
                    "title": item["title"],
                    "show_date": item["show_date"],
                    "feature_count": item["feature_count"],
                }
                for item in movie_payloads
            ]
            movie_features = {str(item["title"]): item["features"] for item in movie_payloads}
        else:
            features = fetch_location_features(conn)
            collection_name = "cinema_locations"
            movies = []
            movie_features = {}

    payload = {
        "type": "FeatureCollection",
        "name": collection_name,
        "generated_at": date.today().isoformat(),
        "movie_title": movie_titles[0] if movie_titles else None,
        "show_date": args.date if movie_titles else None,
        "movies": movies,
        "movie_features": movie_features,
        "feature_count": len(features),
        "features": features,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"GeoJSON exported: {args.output}")
    if movie_titles:
        for movie in movies:
            print(f"{movie['title']}: {movie['feature_count']} features")
    else:
        print(f"Features: {len(features)}")


if __name__ == "__main__":
    main()
