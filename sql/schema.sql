PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cinema_chains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_name TEXT NOT NULL,
    official_url TEXT,
    crawl_url TEXT,
    booking_url TEXT,
    all_locations_assumed_showing INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (chain_name)
);

CREATE TABLE IF NOT EXISTS cinema_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id INTEGER NOT NULL,
    location_name TEXT NOT NULL,
    display_name TEXT,
    address TEXT,
    city TEXT,
    district TEXT,
    latitude REAL,
    longitude REAL,
    source_location_code TEXT,
    location_url TEXT,
    source_url TEXT,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chain_id) REFERENCES cinema_chains (id) ON DELETE CASCADE,
    UNIQUE (chain_id, location_name)
);

CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    original_title TEXT,
    release_date TEXT,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (title, release_date)
);

CREATE TABLE IF NOT EXISTS movie_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_id INTEGER NOT NULL,
    chain_id INTEGER NOT NULL,
    location_id INTEGER,
    target_scope TEXT NOT NULL DEFAULT 'chain_all_locations'
        CHECK (target_scope IN ('chain_all_locations', 'single_location')),
    status TEXT NOT NULL DEFAULT 'assumed_showing'
        CHECK (status IN ('assumed_showing', 'confirmed_showing', 'not_showing', 'unknown')),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (movie_id) REFERENCES movies (id) ON DELETE CASCADE,
    FOREIGN KEY (chain_id) REFERENCES cinema_chains (id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES cinema_locations (id) ON DELETE CASCADE,
    UNIQUE (movie_id, chain_id, location_id)
);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL CHECK (run_type IN ('locations', 'showtimes', 'kml_export', 'other')),
    movie_id INTEGER,
    source_name TEXT,
    source_url TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'failed', 'partial')),
    rows_found INTEGER NOT NULL DEFAULT 0,
    rows_saved INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    FOREIGN KEY (movie_id) REFERENCES movies (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS raw_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_run_id INTEGER,
    source_url TEXT NOT NULL,
    local_path TEXT,
    content_sha256 TEXT,
    http_status INTEGER,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (crawl_run_id) REFERENCES crawl_runs (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS showtimes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    crawl_run_id INTEGER,
    show_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    auditorium TEXT,
    format TEXT,
    language TEXT,
    subtitle TEXT,
    booking_url TEXT,
    source_url TEXT,
    raw_text TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (movie_id) REFERENCES movies (id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES cinema_locations (id) ON DELETE CASCADE,
    FOREIGN KEY (crawl_run_id) REFERENCES crawl_runs (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_showtimes_identity
ON showtimes (
    movie_id,
    location_id,
    show_date,
    start_time,
    ifnull(format, ''),
    ifnull(language, ''),
    ifnull(subtitle, ''),
    ifnull(booking_url, '')
);

CREATE TABLE IF NOT EXISTS kml_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_id INTEGER,
    export_date TEXT,
    file_path TEXT NOT NULL,
    placemark_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (movie_id) REFERENCES movies (id) ON DELETE SET NULL
);

CREATE VIEW IF NOT EXISTS v_location_map_points AS
SELECT
    cl.id AS location_id,
    cc.chain_name,
    cl.location_name,
    COALESCE(cl.display_name, cc.chain_name || ' ' || cl.location_name) AS map_name,
    cl.address,
    cl.city,
    cl.district,
    cl.latitude,
    cl.longitude,
    cl.location_url,
    cc.official_url,
    cc.crawl_url,
    cc.all_locations_assumed_showing
FROM cinema_locations cl
JOIN cinema_chains cc ON cc.id = cl.chain_id
WHERE cc.active = 1
  AND cl.active = 1;

CREATE VIEW IF NOT EXISTS v_showtime_map_points AS
SELECT
    s.id AS showtime_id,
    m.title AS movie_title,
    cc.chain_name,
    cl.location_name,
    COALESCE(cl.display_name, cc.chain_name || ' ' || cl.location_name) AS map_name,
    cl.address,
    cl.city,
    cl.district,
    cl.latitude,
    cl.longitude,
    s.show_date,
    s.start_time,
    s.end_time,
    s.auditorium,
    s.format,
    s.language,
    s.subtitle,
    s.booking_url,
    s.source_url
FROM showtimes s
JOIN movies m ON m.id = s.movie_id
JOIN cinema_locations cl ON cl.id = s.location_id
JOIN cinema_chains cc ON cc.id = cl.chain_id
WHERE cc.active = 1
  AND cl.active = 1
  AND m.active = 1;

CREATE TRIGGER IF NOT EXISTS trg_cinema_chains_updated_at
AFTER UPDATE ON cinema_chains
FOR EACH ROW
BEGIN
    UPDATE cinema_chains SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_cinema_locations_updated_at
AFTER UPDATE ON cinema_locations
FOR EACH ROW
BEGIN
    UPDATE cinema_locations SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_movies_updated_at
AFTER UPDATE ON movies
FOR EACH ROW
BEGIN
    UPDATE movies SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_movie_targets_updated_at
AFTER UPDATE ON movie_targets
FOR EACH ROW
BEGIN
    UPDATE movie_targets SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_showtimes_updated_at
AFTER UPDATE ON showtimes
FOR EACH ROW
BEGIN
    UPDATE showtimes SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;
