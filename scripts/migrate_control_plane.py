"""Extract the live Render control plane into version-controlled GitHub data.

This command is intentionally fail-closed. It writes canonical files only after:
1) the full protected export validates;
2) local tracked-movie selection exactly matches the current /api/tracked-movies/ view;
3) local active cinema master exactly matches the current /api/cinema-master/ view.

It is the migration Gate for Render/Postgres retirement, not a best-effort importer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import control_data  # noqa: E402
import muse_api  # noqa: E402

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_DIR / "artifacts" / "control-plane-migration.json"


def _fetch(endpoint: str, attempts: int = 8, timeout: int = 60):
    base = muse_api.api_base()
    if not base:
        raise RuntimeError("MUSE_API_BASE_URL is required for migration")
    if not muse_api.api_token():
        raise RuntimeError("MUSE_API_TOKEN is required for migration")
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            status, payload = muse_api._request(f"{base}{endpoint}", timeout=timeout)
            if status != 200:
                raise RuntimeError(f"HTTP {status} from {endpoint}")
            return payload
        except Exception as exc:  # Render cold start / deploy window
            last_exc = exc
            if attempt == attempts:
                break
            print(
                f"[migration] {endpoint} attempt {attempt}/{attempts} failed: "
                f"{type(exc).__name__}: {exc}; retrying…",
                file=sys.stderr,
            )
            time.sleep(15)
    raise RuntimeError(f"unable to fetch {endpoint}: {last_exc}")


def _sha(payload) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload) -> None:
    control_data._atomic_json_write(path, payload)


def build_canonical(export_payload: dict) -> tuple[dict, dict]:
    if export_payload.get("schema_version") != 1:
        raise ValueError("control-export schema_version must be 1")
    tracked = export_payload.get("tracked_movies")
    chains = export_payload.get("chains")
    locations = export_payload.get("locations")
    if not isinstance(tracked, list) or not isinstance(chains, list) or not isinstance(locations, list):
        raise ValueError("control-export is missing tracked_movies/chains/locations")

    counts = export_payload.get("counts") or {}
    expected = {
        "tracked_movies": len(tracked),
        "chains": len(chains),
        "locations": len(locations),
    }
    if counts != expected:
        raise ValueError(f"control-export counts mismatch: response={counts} actual={expected}")

    tracked_payload = {
        "schema_version": 1,
        "generated_at": export_payload.get("generated_at"),
        "version": export_payload.get("tracked_movies_version", 0),
        "lookahead_days": control_data.TRACKED_MOVIE_LOOKAHEAD_DAYS,
        "movies": tracked,
    }
    cinema_payload = {
        "schema_version": 1,
        "generated_at": export_payload.get("generated_at"),
        "chains": chains,
        "locations": locations,
    }
    control_data.validate_tracked_movies(tracked_payload)
    control_data.validate_cinema_master(cinema_payload)
    return tracked_payload, cinema_payload


def assert_movie_parity(tracked_payload: dict, old_payload: dict) -> None:
    if not isinstance(old_payload, dict) or not isinstance(old_payload.get("movies"), list):
        raise ValueError("legacy tracked-movies payload is invalid")
    local = control_data.runtime_movie_payload(
        tracked_payload,
        datetime.now(TAIPEI_TZ).date(),
    )
    comparable_local = {
        "version": local.get("version"),
        "count": local.get("count"),
        "movies": local.get("movies"),
    }
    comparable_old = {
        "version": old_payload.get("version"),
        "count": old_payload.get("count"),
        "movies": old_payload.get("movies"),
    }
    if comparable_local != comparable_old:
        raise ValueError(
            "tracked-movie parity FAILED\n"
            + json.dumps(
                {"local": comparable_local, "legacy": comparable_old},
                ensure_ascii=False,
                indent=2,
            )
        )


def assert_cinema_parity(cinema_payload: dict, old_payload: dict) -> None:
    local = control_data.active_cinema_payload(cinema_payload)
    comparable_local = {
        "chain_count": local["chain_count"],
        "location_count": local["location_count"],
        "chains": local["chains"],
        "locations": local["locations"],
    }
    comparable_old = {
        "chain_count": old_payload.get("chain_count"),
        "location_count": old_payload.get("location_count"),
        "chains": old_payload.get("chains"),
        "locations": old_payload.get("locations"),
    }
    if comparable_local != comparable_old:
        raise ValueError(
            "cinema-master parity FAILED\n"
            + json.dumps(
                {"local": comparable_local, "legacy": comparable_old},
                ensure_ascii=False,
                indent=2,
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Render control data to GitHub files.")
    parser.add_argument("--tracked-output", type=Path, default=control_data.TRACKED_MOVIES_PATH)
    parser.add_argument("--cinema-output", type=Path, default=control_data.CINEMA_MASTER_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    export_payload = _fetch("/api/control-export/")
    tracked_payload, cinema_payload = build_canonical(export_payload)

    # Independent reads of the legacy runtime endpoints are the first parity gate.
    old_movies = _fetch("/api/tracked-movies/")
    old_cinemas = _fetch("/api/cinema-master/")
    assert_movie_parity(tracked_payload, old_movies)
    assert_cinema_parity(cinema_payload, old_cinemas)

    # Only now is it safe to materialize GitHub canonical state.
    _write_json(args.tracked_output, tracked_payload)
    _write_json(args.cinema_output, cinema_payload)

    active_movies = [m for m in tracked_payload["movies"] if m["is_active"]]
    inactive_movies = [m for m in tracked_payload["movies"] if not m["is_active"]]
    coded_locations = [
        loc for loc in cinema_payload["locations"]
        if (loc.get("source_location_code") or "").strip()
    ]
    report = {
        "status": "PASS",
        "generated_at": datetime.now(TAIPEI_TZ).isoformat(),
        "gates": {
            "full_export_valid": True,
            "tracked_movie_runtime_parity": True,
            "cinema_master_runtime_parity": True,
        },
        "counts": {
            "tracked_movies_total": len(tracked_payload["movies"]),
            "tracked_movies_active": len(active_movies),
            "tracked_movies_inactive": len(inactive_movies),
            "chains_total": len(cinema_payload["chains"]),
            "locations_total": len(cinema_payload["locations"]),
            "locations_with_source_code": len(coded_locations),
        },
        "sha256": {
            "tracked_movies": _sha(tracked_payload),
            "cinema_master": _sha(cinema_payload),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
