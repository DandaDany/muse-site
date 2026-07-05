# Technical Decisions

This file records technical choices that are considered confirmed for this project. It is meant to answer "why is it built this way?" without searching through the working log.

## Frontend Map

- Use Leaflet for the browser map.
  - Reason: the project is a lightweight static map and Leaflet works well with plain HTML/CSS/JavaScript.
  - Current files: `web/index.html`, `web/app.js`, `web/styles.css`.

- Keep the public map as a static site under `web/`.
  - Reason: GitHub Pages can deploy it directly without a backend server.
  - The map reads generated data from `web/data/locations.geojson`.

- Use GeoJSON as the frontend data contract.
  - Reason: it is a natural fit for map point data and keeps the frontend independent from SQLite.
  - Export script: `scripts/export_geojson.py`.

- Support multiple movies in one GeoJSON payload.
  - Reason: the public map can switch movies with a dropdown without fetching separate files.
  - Current frontend state:
    - `movies`
    - `movie_features`
    - selected movie title in `web/app.js`.

## Marker Logos

- Use `web/data/chain_logos.json` as the chain-name to logo-path mapping.
  - Reason: adding or correcting logos should not require changing marker JavaScript.
  - Logo files live in `web/assets/logos/`.

- Render cinema logos with CSS `background-image`, not `<img>`.
  - Reason: `<img>` inside Leaflet `divIcon` rendered at natural image size and overflowed the small marker, causing white-circle markers.
  - Confirmed fix:
    - JS sets `--marker-logo: url(...)`.
    - CSS uses `background-image: var(--marker-logo)` and `background-size: cover`.

- Keep the original text marker fallback.
  - Reason: if a chain has no logo mapping, the map should still show a usable marker.

- Marker size is based on `showtime_count`.
  - Reason: theaters with more showtimes should be visually emphasized.
  - Current range: `MIN_MARKER_SIZE = 24`, `MAX_MARKER_SIZE = 48`.

- Smaller markers are rendered above larger markers with `zIndexOffset`.
  - Reason: theaters with fewer showtimes have smaller logos and would otherwise be hidden when overlapping larger logos.
  - Current rule: `zIndexOffset = (MAX_MARKER_SIZE - markerSize(feature)) * 1000`.

## Data Pipeline

- Use SQLite as the local working database.
  - Reason: it keeps crawl/import/export scripts simple and portable.
  - Default database: `data/movie_map.sqlite`.
  - The SQLite file is ignored by Git and should not be published.

- Use Python scripts for crawling, importing, and exporting.
  - Reason: the project is data-heavy, and Python has good HTML, JSON, and SQLite tooling.

- Use BeautifulSoup for static HTML parsing.
  - Reason: many cinema pages can be parsed from HTML responses without a browser.

- Use Playwright when a site requires browser behavior.
  - Confirmed use cases:
    - Capturing short-lived Shin Kong Cinemas API headers.
    - Handling VIESHOW/MUVIE browser-only behavior and visible select menus.
  - Reason: some cinema sources depend on browser-generated state, hidden selects, or dynamic API headers.

- Keep raw crawl output under `data/output/`.
  - Reason: debugging source-site changes is easier with raw responses.
  - This folder is ignored by Git except for `.gitkeep`.

## Movie Matching

- Movie title matching is normalized, not exact-only.
  - Current normalization:
    - full-width digits to half-width digits
    - lowercase English
    - remove common spaces and punctuation
  - This handles examples like `玩具總動員5`, `玩具總動員 5`, and `玩具總動員５`.

- Keep aliases available for movie matching.
  - Current implementation supports repeated `--alias` in `scripts/fetch_movie_showtimes.py`.
  - `玩具總動員5` has extra built-in aliases such as `Toy Story 5`.

- Use `電影清單.txt` as the default multi-movie input list.
  - Reason: non-technical updates should be easy: edit a numbered text file, then run the batch file.

## Publishing

- Deploy the public map with GitHub Pages and GitHub Actions.
  - Repository: `https://github.com/DandaDany/muse_movie_screeing_time`
  - Public site: `https://dandadany.github.io/muse_movie_screeing_time/`
  - Workflow file: `.github/workflows/pages.yml`.

- Deploy only `web/` to GitHub Pages.
  - Reason: the public site only needs the static app and generated GeoJSON/assets.
  - Local database and raw crawl outputs stay private.

- Use `更新地圖.bat` as the one-click local update and publish command.
  - Current flow:
    - run `scripts/update_map.py`
    - generate `web/data/locations.geojson`
    - `git add .`
    - commit if there are changes
    - `git push`
  - GitHub Actions then deploys automatically.

## Basemaps

- Use a single fixed basemap: CARTO Voyager. No basemap picker in the UI.
  - Reason: one good default keeps the sidebar simple; the picker added a control without real value.

## Sidebar Layout

- Sidebar summary line format: `{電影}：{N} 影城上映中，共 {M} 場次` (counts follow active filters).
- No standalone stats tiles (顯示/總點位) — the summary line carries the numbers.
- Filter lists (品牌/縣市) use fixed pixel max-heights (rows-based), not `vh`.
  - Reason: `vh`-based heights collapsed to a single visible row on short phone screens.
- Sidebar children use `flex: 0 0 auto` so blocks never get flex-compressed; the sidebar itself scrolls when space runs out.

## Files That Should Stay Out Of Git

- `data/movie_map.sqlite`
- `data/*.sqlite-shm`
- `data/*.sqlite-wal`
- `data/output/*`
- `scripts/__pycache__/`
- `.agents/`
- `.codex/`
- `工作日誌.txt`

These are excluded in `.gitignore` because they are local state, debug output, or private working notes.
