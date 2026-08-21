"""Shared movie-title normalization and alias lookup for showtime crawlers.

Typography differences between the backend title and cinema websites are treated
as presentation noise. NFKC normalization handles full-width/half-width forms
before the existing punctuation-insensitive substring comparison.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MOVIE_CACHE = PROJECT_DIR / "cache" / "tracked_movies.json"

_PUNCTUATION_RE = re.compile(
    r"[\s　:：,，.。、/／()（）\[\]【】{}｛｝<>＜＞「」『』《》〈〉"
    r"\-–—_．・‧|｜'\"“”‘’!！?？~～+＋]+"
)


def normalize_text(value: str | None) -> str:
    """Normalize typography before comparing movie titles."""
    if not value:
        return ""
    value = html.unescape(value)
    value = unicodedata.normalize("NFKC", value).casefold()
    return _PUNCTUATION_RE.sub("", value)


def movie_matches(text: str | None, aliases: list[str]) -> bool:
    """Match normalized canonical titles/aliases as substrings of source text."""
    normalized_text = normalize_text(text)
    if not normalized_text:
        return False
    normalized_aliases = {
        normalize_text(alias)
        for alias in aliases
        if isinstance(alias, str) and alias.strip()
    }
    normalized_aliases.discard("")
    return any(alias in normalized_text for alias in normalized_aliases)


def aliases_for_titles(
    titles: list[str],
    cache_path: Path = DEFAULT_MOVIE_CACHE,
) -> dict[str, list[str]]:
    """Read backend aliases from the existing tracked-movie API cache.

    The daily worker already writes the complete ``/api/tracked-movies/``
    payload to ``cache/tracked_movies.json`` before updating ``電影清單.txt``.
    Missing or invalid cache data stays non-fatal for local/manual runs.
    """
    wanted = set(titles)
    result = {title: [] for title in titles}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return result

    movies = payload.get("movies") if isinstance(payload, dict) else None
    if not isinstance(movies, list):
        return result

    for movie in movies:
        if not isinstance(movie, dict):
            continue
        title = movie.get("title")
        if title not in wanted:
            continue
        raw_aliases = movie.get("aliases")
        if not isinstance(raw_aliases, list):
            continue
        seen: set[str] = set()
        aliases: list[str] = []
        for alias in raw_aliases:
            if not isinstance(alias, str):
                continue
            alias = alias.strip()
            if not alias or alias == title or alias in seen:
                continue
            seen.add(alias)
            aliases.append(alias)
        result[title] = aliases
    return result
