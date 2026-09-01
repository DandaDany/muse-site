"""Shared movie-title normalization and alias lookup for showtime crawlers.

Typography differences between the backend title and cinema websites are treated
as presentation noise. NFKC normalization handles full-width/half-width forms
before the existing punctuation-insensitive substring comparison.

Backend aliases remain the primary runtime source. A small version-controlled
alias file can supplement them when a tracked internal title intentionally differs
from the title used by cinema ticketing systems; this keeps source-specific names
out of crawler code and makes the exception auditable in git.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MOVIE_CACHE = PROJECT_DIR / "cache" / "tracked_movies.json"
DEFAULT_ALIAS_OVERRIDES = PROJECT_DIR / "data" / "input" / "movie_aliases.json"

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


def _load_alias_overrides(path: Path) -> dict[str, list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(payload, dict):
        return {}

    result: dict[str, list[str]] = {}
    for title, raw_aliases in payload.items():
        if not isinstance(title, str) or not isinstance(raw_aliases, list):
            continue
        aliases = [
            alias.strip()
            for alias in raw_aliases
            if isinstance(alias, str) and alias.strip()
        ]
        result[title] = aliases
    return result


def aliases_for_titles(
    titles: list[str],
    cache_path: Path = DEFAULT_MOVIE_CACHE,
    override_path: Path = DEFAULT_ALIAS_OVERRIDES,
) -> dict[str, list[str]]:
    """Merge backend aliases with version-controlled official-title aliases.

    The daily worker writes the complete ``/api/tracked-movies/`` payload to
    ``cache/tracked_movies.json`` before updating ``電影清單.txt``. Backend aliases
    are read from that cache. ``data/input/movie_aliases.json`` may supplement the
    backend for internal tracking names that intentionally differ from cinema
    ticketing titles. Missing/invalid files are non-fatal for local/manual runs.
    """
    wanted = set(titles)
    result = {title: [] for title in titles}

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        payload = None

    movies = payload.get("movies") if isinstance(payload, dict) else None
    if isinstance(movies, list):
        for movie in movies:
            if not isinstance(movie, dict):
                continue
            title = movie.get("title")
            if title not in wanted:
                continue
            raw_aliases = movie.get("aliases")
            if not isinstance(raw_aliases, list):
                continue
            for alias in raw_aliases:
                if isinstance(alias, str):
                    result[title].append(alias.strip())

    overrides = _load_alias_overrides(override_path)
    for title in titles:
        result[title].extend(overrides.get(title, []))

    for title in titles:
        seen: set[str] = set()
        cleaned: list[str] = []
        for alias in result[title]:
            if not alias or alias == title or alias in seen:
                continue
            seen.add(alias)
            cleaned.append(alias)
        result[title] = cleaned

    return result
