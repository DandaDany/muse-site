-- Postgres 版業務表 schema（控制面雲端 Postgres 用）
--
-- 為什麼需要這份：sql/schema.sql 是 SQLite 語法（AUTOINCREMENT、INTEGER 布林等），
-- Postgres 不能直接執行。這 8 張表在後台是 unmanaged models（managed=False），
-- 所以 Django migrate 不會建立它們；在全新的雲端 Postgres 上必須靠這份 DDL 先建好，
-- 否則 /admin 的影城/場次頁會因找不到表而報錯。
--
-- 型別對映刻意對齊 backend/mapdata/models.py 的欄位型別：
--   CharField 日期時間欄位（created_at/updated_at/show_date/start_time…）-> TEXT
--   BooleanField（active/all_locations_assumed_showing）               -> BOOLEAN
--   FloatField（latitude/longitude）                                    -> DOUBLE PRECISION
--   IntegerField（rows_found/http_status/placemark_count…）             -> INTEGER
--
-- 全部使用 CREATE TABLE IF NOT EXISTS，可重複執行（idempotent）。
-- 說明：本控制面 Postgres 只需「表存在」供後台讀寫；SQLite 專屬的 view / trigger
-- （v_location_map_points、updated_at 觸發器等）屬爬蟲/匯出流程，仍在爬蟲面 SQLite 使用，
-- 不在此重建。

CREATE TABLE IF NOT EXISTS cinema_chains (
    id SERIAL PRIMARY KEY,
    chain_name TEXT NOT NULL,
    official_url TEXT,
    crawl_url TEXT,
    booking_url TEXT,
    all_locations_assumed_showing BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TEXT DEFAULT (now()::text),
    updated_at TEXT DEFAULT (now()::text),
    UNIQUE (chain_name)
);

CREATE TABLE IF NOT EXISTS cinema_locations (
    id SERIAL PRIMARY KEY,
    chain_id INTEGER NOT NULL REFERENCES cinema_chains (id) ON DELETE CASCADE,
    location_name TEXT NOT NULL,
    display_name TEXT,
    address TEXT,
    city TEXT,
    district TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    source_location_code TEXT,
    location_url TEXT,
    source_url TEXT,
    notes TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TEXT DEFAULT (now()::text),
    updated_at TEXT DEFAULT (now()::text),
    UNIQUE (chain_id, location_name)
);

CREATE TABLE IF NOT EXISTS movies (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    original_title TEXT,
    release_date TEXT,
    notes TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TEXT DEFAULT (now()::text),
    updated_at TEXT DEFAULT (now()::text),
    UNIQUE (title, release_date)
);

CREATE TABLE IF NOT EXISTS movie_targets (
    id SERIAL PRIMARY KEY,
    movie_id INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    chain_id INTEGER NOT NULL REFERENCES cinema_chains (id) ON DELETE CASCADE,
    location_id INTEGER REFERENCES cinema_locations (id) ON DELETE CASCADE,
    target_scope TEXT NOT NULL DEFAULT 'chain_all_locations'
        CHECK (target_scope IN ('chain_all_locations', 'single_location')),
    status TEXT NOT NULL DEFAULT 'assumed_showing'
        CHECK (status IN ('assumed_showing', 'confirmed_showing', 'not_showing', 'unknown')),
    notes TEXT,
    created_at TEXT DEFAULT (now()::text),
    updated_at TEXT DEFAULT (now()::text),
    UNIQUE (movie_id, chain_id, location_id)
);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id SERIAL PRIMARY KEY,
    run_type TEXT NOT NULL CHECK (run_type IN ('locations', 'showtimes', 'kml_export', 'other')),
    movie_id INTEGER REFERENCES movies (id) ON DELETE SET NULL,
    source_name TEXT,
    source_url TEXT,
    started_at TEXT DEFAULT (now()::text),
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'failed', 'partial')),
    rows_found INTEGER NOT NULL DEFAULT 0,
    rows_saved INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS raw_pages (
    id SERIAL PRIMARY KEY,
    crawl_run_id INTEGER REFERENCES crawl_runs (id) ON DELETE SET NULL,
    source_url TEXT NOT NULL,
    local_path TEXT,
    content_sha256 TEXT,
    http_status INTEGER,
    fetched_at TEXT DEFAULT (now()::text)
);

CREATE TABLE IF NOT EXISTS showtimes (
    id SERIAL PRIMARY KEY,
    movie_id INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES cinema_locations (id) ON DELETE CASCADE,
    crawl_run_id INTEGER REFERENCES crawl_runs (id) ON DELETE SET NULL,
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
    created_at TEXT DEFAULT (now()::text),
    updated_at TEXT DEFAULT (now()::text)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_showtimes_identity
ON showtimes (
    movie_id,
    location_id,
    show_date,
    start_time,
    COALESCE(format, ''),
    COALESCE(language, ''),
    COALESCE(subtitle, ''),
    COALESCE(booking_url, '')
);

CREATE TABLE IF NOT EXISTS kml_exports (
    id SERIAL PRIMARY KEY,
    movie_id INTEGER REFERENCES movies (id) ON DELETE SET NULL,
    export_date TEXT,
    file_path TEXT NOT NULL,
    placemark_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (now()::text)
);
