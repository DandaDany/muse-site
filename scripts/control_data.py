from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]
CONTROL_DIR = PROJECT_DIR / "data" / "control"
TRACKED_MOVIES_PATH = CONTROL_DIR / "tracked_movies.json"
CINEMA_MASTER_PATH = CONTROL_DIR / "cinema_master.json"
MOVIE_LIST_PATH = PROJECT_DIR / "電影清單.txt"
TRACKED_MOVIE_LOOKAHEAD_DAYS = 7

TRACKED_REQUIRED = {"title", "aliases", "target_date", "is_active", "sort_order", "notes"}
CHAIN_REQUIRED = {
    "id", "chain_name", "official_url", "crawl_url", "booking_url",
    "all_locations_assumed_showing", "notes", "active",
}
LOCATION_REQUIRED = {
    "id", "chain_id", "location_name", "display_name", "address", "city", "district",
    "latitude", "longitude", "source_location_code", "location_url", "source_url", "notes", "active",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def validate_tracked_movies(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != 1:
        raise ValueError("tracked_movies schema_version must be 1")
    movies = payload.get("movies")
    if not isinstance(movies, list):
        raise ValueError("tracked_movies.movies must be a list")
    seen: set[str] = set()
    for idx, movie in enumerate(movies):
        if not isinstance(movie, dict):
            raise ValueError(f"tracked_movies.movies[{idx}] must be an object")
        missing = TRACKED_REQUIRED - set(movie)
        if missing:
            raise ValueError(f"tracked movie missing fields: {sorted(missing)}")
        title = movie.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("tracked movie title must be non-empty")
        if title in seen:
            raise ValueError(f"duplicate tracked movie title: {title}")
        seen.add(title)
        aliases = movie.get("aliases")
        if not isinstance(aliases, list) or any(not isinstance(v, str) for v in aliases):
            raise ValueError(f"aliases must be list[str] for {title}")
        target_date = movie.get("target_date")
        if target_date is not None:
            date.fromisoformat(target_date)
        if not isinstance(movie.get("is_active"), bool):
            raise ValueError(f"is_active must be bool for {title}")
        if not isinstance(movie.get("sort_order"), int):
            raise ValueError(f"sort_order must be int for {title}")
    return payload


def validate_cinema_master(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != 1:
        raise ValueError("cinema_master schema_version must be 1")
    chains = payload.get("chains")
    locations = payload.get("locations")
    if not isinstance(chains, list) or not isinstance(locations, list):
        raise ValueError("cinema_master chains/locations must be lists")

    chain_ids: set[int] = set()
    chain_names: set[str] = set()
    for chain in chains:
        if not isinstance(chain, dict):
            raise ValueError("chain must be an object")
        missing = CHAIN_REQUIRED - set(chain)
        if missing:
            raise ValueError(f"cinema chain missing fields: {sorted(missing)}")
        cid = chain.get("id")
        name = chain.get("chain_name")
        if not isinstance(cid, int) or cid in chain_ids:
            raise ValueError(f"invalid/duplicate cinema chain id: {cid}")
        if not isinstance(name, str) or not name.strip() or name in chain_names:
            raise ValueError(f"invalid/duplicate cinema chain name: {name}")
        chain_ids.add(cid)
        chain_names.add(name)

    location_ids: set[int] = set()
    natural_keys: set[tuple[int, str]] = set()
    for loc in locations:
        if not isinstance(loc, dict):
            raise ValueError("location must be an object")
        missing = LOCATION_REQUIRED - set(loc)
        if missing:
            raise ValueError(f"cinema location missing fields: {sorted(missing)}")
        lid = loc.get("id")
        cid = loc.get("chain_id")
        name = loc.get("location_name")
        if not isinstance(lid, int) or lid in location_ids:
            raise ValueError(f"invalid/duplicate cinema location id: {lid}")
        if cid not in chain_ids:
            raise ValueError(f"location {name} references missing chain_id={cid}")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("location_name must be non-empty")
        nk = (cid, name)
        if nk in natural_keys:
            raise ValueError(f"duplicate cinema location natural key: {nk}")
        location_ids.add(lid)
        natural_keys.add(nk)
    return payload


def load_tracked_movies(path: Path = TRACKED_MOVIES_PATH) -> dict[str, Any]:
    return validate_tracked_movies(_read_json(path))


def load_cinema_master(path: Path = CINEMA_MASTER_PATH) -> dict[str, Any]:
    return validate_cinema_master(_read_json(path))


def eligible_movies(
    payload: dict[str, Any],
    as_of: date,
    lookahead_days: int = TRACKED_MOVIE_LOOKAHEAD_DAYS,
) -> list[dict[str, Any]]:
    validate_tracked_movies(payload)
    horizon = as_of + timedelta(days=lookahead_days)
    eligible: list[dict[str, Any]] = []
    for movie in payload["movies"]:
        if not movie["is_active"]:
            continue
        raw_target = movie.get("target_date")
        if raw_target is not None and date.fromisoformat(raw_target) > horizon:
            continue
        eligible.append(movie)
    return sorted(eligible, key=lambda m: (m.get("sort_order", 0), m["title"]))


def runtime_movie_payload(payload: dict[str, Any], as_of: date) -> dict[str, Any]:
    movies = eligible_movies(payload, as_of)
    return {
        "generated_at": payload.get("generated_at"),
        "version": payload.get("version", 0),
        "count": len(movies),
        "movies": [
            {
                "id": m.get("id"),
                "title": m["title"],
                "aliases": list(m.get("aliases") or []),
                "target_date": m.get("target_date"),
                "enabled": True,
                "updated_at": m.get("updated_at"),
            }
            for m in movies
        ],
    }


def write_runtime_movie_files(
    payload: dict[str, Any],
    as_of: date,
    movie_list_path: Path = MOVIE_LIST_PATH,
    cache_path: Path | None = None,
) -> dict[str, Any]:
    runtime_payload = runtime_movie_payload(payload, as_of)
    lines = [f"{i}. {m['title']}" for i, m in enumerate(runtime_payload["movies"], start=1)]
    movie_list_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = movie_list_path.with_suffix(movie_list_path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8-sig")
    os.replace(tmp, movie_list_path)
    if cache_path is not None:
        _atomic_json_write(cache_path, runtime_payload)
    return runtime_payload


def active_cinema_payload(payload: dict[str, Any]) -> dict[str, Any]:
    validate_cinema_master(payload)
    active_chains = [c for c in payload["chains"] if c.get("active")]
    active_ids = {c["id"] for c in active_chains}
    active_locations = [loc for loc in payload["locations"] if loc.get("active")]
    dangling = [loc for loc in active_locations if loc.get("chain_id") not in active_ids]
    if dangling:
        names = ", ".join(loc["location_name"] for loc in dangling[:5])
        raise ValueError(f"active locations reference inactive/missing chains: {names}")
    return {
        "generated_at": payload.get("generated_at"),
        "chain_count": len(active_chains),
        "location_count": len(active_locations),
        "chains": active_chains,
        "locations": active_locations,
    }


def persist_codes_from_sqlite(
    db_path: Path,
    master_path: Path = CINEMA_MASTER_PATH,
) -> tuple[int, int]:
    payload = load_cinema_master(master_path)
    chain_by_id = {c["id"]: c for c in payload["chains"]}
    location_by_key = {
        (chain_by_id[loc["chain_id"]]["chain_name"], loc["location_name"]): loc
        for loc in payload["locations"]
    }

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT cc.chain_name, cl.location_name, cl.source_location_code
            FROM cinema_locations cl
            JOIN cinema_chains cc ON cc.id = cl.chain_id
            WHERE cl.source_location_code IS NOT NULL
              AND TRIM(cl.source_location_code) <> ''
            """
        ).fetchall()
    finally:
        con.close()

    updated = skipped = 0
    for row in rows:
        key = (row["chain_name"], row["location_name"])
        loc = location_by_key.get(key)
        if loc is None:
            skipped += 1
            continue
        code = row["source_location_code"].strip()
        if (loc.get("source_location_code") or "").strip() == code:
            continue
        loc["source_location_code"] = code
        updated += 1

    if updated:
        _atomic_json_write(master_path, payload)
    return updated, skipped
