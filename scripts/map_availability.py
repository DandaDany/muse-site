from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def feature_has_real_showtimes(feature: dict[str, Any]) -> bool:
    """Return True only when a feature contains at least one actual showtime."""
    props = feature.get("properties") or {}
    count = props.get("showtime_count")
    if isinstance(count, (int, float)) and count > 0:
        return True
    showtimes = props.get("showtimes")
    return isinstance(showtimes, list) and len(showtimes) > 0


def date_has_real_showtimes(features: list[dict[str, Any]]) -> bool:
    """Fallback/unavailable pins are not evidence that a movie is available that day."""
    return any(feature_has_real_showtimes(feature) for feature in features)


def sanitize_movie_availability(payload: dict[str, Any], primary_date: str) -> dict[str, Any]:
    """Normalize movie/date availability after GeoJSON export.

    Rules:
    - a date is selectable only when it has at least one real showtime;
    - unavailable/fallback pins may stay alongside real showtimes on a valid date;
    - movies with no real showtimes in the exported window stay out of the selector;
    - movies with real showtimes on the primary date are ordered before future-only movies.

    This prevents an upcoming tracked title with a synthetic 0-showtime fallback pin
    from becoming the default movie and making the map look broken.
    """
    by_movie = payload.get("movie_features_by_date")
    if not isinstance(by_movie, dict):
        return payload

    cleaned_by_movie: dict[str, dict[str, list[dict[str, Any]]]] = {}
    today_titles: list[str] = []
    future_titles: list[str] = []

    for title, by_date in by_movie.items():
        if not isinstance(by_date, dict):
            continue
        cleaned_dates: dict[str, list[dict[str, Any]]] = {}
        for show_date, features in by_date.items():
            if not isinstance(features, list):
                continue
            if date_has_real_showtimes(features):
                # Keep all features for a valid date so a source-unavailable pin can
                # coexist with real showtimes from other cinemas.
                cleaned_dates[show_date] = features
        if not cleaned_dates:
            continue
        cleaned_by_movie[title] = cleaned_dates
        if primary_date in cleaned_dates:
            today_titles.append(title)
        else:
            future_titles.append(title)

    ordered_titles = [*today_titles, *future_titles]
    cleaned_by_movie = {title: cleaned_by_movie[title] for title in ordered_titles}

    summaries_by_title = {
        item.get("title"): item
        for item in payload.get("movies", [])
        if isinstance(item, dict) and item.get("title")
    }
    movies: list[dict[str, Any]] = []
    for title in ordered_titles:
        original = dict(summaries_by_title.get(title) or {"title": title})
        valid_dates = list(cleaned_by_movie[title].keys())
        original["show_date"] = primary_date
        original["available_dates"] = valid_dates
        original["feature_count"] = len(cleaned_by_movie[title].get(primary_date, []))
        movies.append(original)

    movie_features = {
        title: cleaned_by_movie[title].get(primary_date, [])
        for title in ordered_titles
    }
    available_dates = list(
        dict.fromkeys(
            show_date
            for title in ordered_titles
            for show_date in cleaned_by_movie[title].keys()
        )
    )

    payload["movies"] = movies
    payload["movie_features"] = movie_features
    payload["movie_features_by_date"] = cleaned_by_movie
    payload["available_dates"] = available_dates

    if ordered_titles:
        default_title = ordered_titles[0]
        primary_features = cleaned_by_movie[default_title].get(primary_date, [])
        payload["movie_title"] = default_title
        payload["features"] = primary_features
        payload["feature_count"] = len(primary_features)
        payload.pop("empty_state", None)
    else:
        payload["movie_title"] = None
        payload["features"] = []
        payload["feature_count"] = 0
        payload["empty_state"] = "no_published_showtimes"

    return payload


def sanitize_geojson_file(path: Path, primary_date: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sanitize_movie_availability(payload, primary_date)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
