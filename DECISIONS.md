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

## Mobile Sheet (≤760px)

- Mobile uses a distinct "墨黑一點橘" theme (paper `#faf9f7` sheet, deep-orange `#e05a12` accent, underline tab bar). The accent is set by overriding `--flame`/`--flame-deep`/`--peach-tint` **only on `.sidebar` inside the media query**, so desktop and the map popups keep the original flame orange.
- Fixed **map 6 / sheet 4** split: the sheet rests showing `40vh` (`REST_VISIBLE_RATIO`), map takes the top `60vh`. Total sheet height is `90vh`; dragging the handle (or tapping it) expands to near-full and snaps back. Only two snap points: `full` / `rest`.
- The sheet floats with left/right/bottom margins (10px) and is fully rounded (24px), not edge-to-edge.
- Search moves **out of the sheet onto the map** (`.m-search`, white pill, top of map). The zoom/attribution controls are pushed down (`.leaflet-top.leaflet-left { top: 62px }`) and a `⌂` reset button floats top-right (`.m-home`). Search suggestions render in `.m-suggestions` over the map.
- A **segmented control** (`.m-seg`, tabs 電影／地區／時間／影城) switches the sheet body via `mtab-*` classes on `.app-shell`:
  - 電影 → `#mMovieList` (片名＋場次, single-select, mirrors the desktop `<select>` through `selectMovie`).
  - 地區 → reuses `#cityFilterList` (縣市 chips).
  - 時間 → `#mTimePanel`: a time-axis slider (`最早場次 HH:MM 之後`, `timeEarliest`) plus quick-period chips 全天／上午／下午／晚上 (`timePeriod`). A cinema passes when it has a showtime in `[max(periodStart, earliest), periodEnd)`; both default to no-op so desktop is unaffected.
  - 影城 → reuses `#chainFilterList` (品牌 chips).
- Search state routes through `activeSearchInput()` / `activeSuggestions()` so the same filter/suggestion code serves the desktop input or the mobile map search depending on `isMobile()`.
- After the transform transition, JS calls `map.invalidateSize()` so Leaflet re-renders tiles at the new container size.
- Desktop is untouched — all of the above is scoped to the `max-width: 760px` media query (mobile-only elements are `display:none` by default) and mobile-only JS guards.

## Location Popup

- Show only 影城名稱 (title) + 地址; drop the `品牌 ｜ 縣市` line.
- Address row has a Google Maps pin link on the right: `https://www.google.com/maps/search/?api=1&query={lat},{lng}` (built from the feature coordinates).
- Showtimes header is `當日, yyyy/mm/dd` (from `show_date`), not movie title.
- Showtime rows: no numbering; large bold time (17px, tabular) + smaller format/auditorium sublabel. About 7 rows visible, the rest scroll.
- Popup height is kept compact (~400px) so it fits inside the mobile map area (which is only ~64vh and clips via `overflow:hidden`); popups use `autoPan`/`keepInView`.

## Marker Click Zoom

- 1st click on a map logo: fly in to `FOCUS_ZOOM` (14, 據點層級) and open the popup.
- Clicking the same logo again while zoomed in: fly back out to `CITY_ZOOM` (11, 縣市層級) and close the popup — not all the way to the Taiwan overview (that stays on the home button).
- Search-suggestion clicks always zoom in (never toggle out).
- Selecting a city filter flies the map to that city's centroid (averaged cinema coordinates) at `CITY_ZOOM` (11).

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
