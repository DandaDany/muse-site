# GitHub Control Plane

This directory replaces the hosted Django/Postgres control plane after the one-time migration is verified.

Canonical files created by the migration workflow:

- `tracked_movies.json` — all tracked movies, including inactive and future rows.
- `cinema_master.json` — all cinema chains and locations, including inactive rows and last-known-good source codes.
- `migration_verification.json` — immutable evidence from the cutover run (counts, hashes, parity gates, production crawl gate).

## Movie maintenance

`tracked_movies.json` is the single source of truth. Do not hand-edit `電影清單.txt`; the daily job generates it from active movies whose `target_date` is no later than seven days from Taiwan today.

Movie fields kept from the former backend:

- `title`
- `aliases`
- `target_date`
- `is_active`
- `sort_order`
- `notes`
- original IDs / timestamps for audit continuity

Prefer `is_active: false` over deleting a movie so history remains reviewable in Git.

## Cinema maintenance

`cinema_master.json` keeps the former backend chain/location records. Runtime source-code refreshers update only non-empty `source_location_code` values back into this file. A failed/blank refresh never erases the last-known-good code.

Existing version-controlled overlays in `data/input/` remain part of the crawler pipeline; this migration intentionally does not refactor crawler source definitions at the same time as removing Render.

## Safety rule

The daily pipeline enables GitHub control mode only when **both** canonical JSON files exist. If only one exists or either file is invalid, the crawl fails closed rather than silently mixing GitHub and Render state.
