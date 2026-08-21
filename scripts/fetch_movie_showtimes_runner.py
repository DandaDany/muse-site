"""Production entrypoint that installs shared movie-title matching then runs crawler.

Keeping this wrapper small lets the legacy all-source crawler reuse one permanent
normalization policy without source-specific title exceptions.
"""

from __future__ import annotations

import fetch_movie_showtimes as crawler
from movie_title_matching import movie_matches, normalize_text

# All existing source parsers call these module globals. Replace them once at
# process startup so every cinema source gets the same Unicode-safe behavior.
crawler.normalize_text = normalize_text
crawler.movie_matches = movie_matches


if __name__ == "__main__":
    crawler.main()
