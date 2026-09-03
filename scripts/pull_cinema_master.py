"""Build the crawler SQLite cinema master from GitHub control data or legacy backend.

Migration behavior:
- If data/control/cinema_master.json exists, it is the canonical source.
- Before migration materializes that file, fall back to legacy /api/cinema-master/.
- A present-but-invalid GitHub master fails closed; it never silently falls back.

The script rebuilds only cinema_chains / cinema_locations in data/movie_map.sqlite.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import control_data  # noqa: E402
import muse_api  # noqa: E402
from init_db import DEFAULT_DB_PATH, init_db  # noqa: E402

CHAIN_COLUMNS = [
    "id", "chain_name", "official_url", "crawl_url", "booking_url",
    "all_locations_assumed_showing", "notes", "active",
]
LOCATION_COLUMNS = [
    "id", "chain_id", "location_name", "display_name", "address", "city",
    "district", "latitude", "longitude", "source_location_code",
    "location_url", "source_url", "notes", "active",
]


def _row(record: dict, columns: list[str]) -> tuple:
    values = []
    for col in columns:
        val = record.get(col)
        if col in ("active", "all_locations_assumed_showing"):
            val = 1 if val else 0
        values.append(val)
    return tuple(values)


def rebuild_master(db_path: Path, payload: dict) -> tuple[int, int]:
    chains = payload["chains"]
    locations = payload["locations"]

    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM cinema_locations")
        conn.execute("DELETE FROM cinema_chains")
        conn.executemany(
            f"INSERT INTO cinema_chains ({', '.join(CHAIN_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in CHAIN_COLUMNS)})",
            [_row(c, CHAIN_COLUMNS) for c in chains],
        )
        conn.executemany(
            f"INSERT INTO cinema_locations ({', '.join(LOCATION_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in LOCATION_COLUMNS)})",
            [_row(loc, LOCATION_COLUMNS) for loc in locations],
        )
        conn.commit()
    return len(chains), len(locations)


def _fetch_legacy_master() -> dict:
    attempts = 5
    payload = None
    last_exc = None
    for i in range(1, attempts + 1):
        try:
            payload = muse_api.fetch_cinema_master(timeout=60)
            if i > 1:
                print(f"[影城主檔] 第 {i} 次嘗試成功（後台已喚醒）。")
            break
        except Exception as exc:
            last_exc = exc
            if i < attempts:
                print(
                    f"[重試 {i}/{attempts}] 後台尚未回應（{type(exc).__name__}: {exc}）；"
                    "等待後重試…",
                    file=sys.stderr,
                )
                time.sleep(15)
    if payload is None:
        raise RuntimeError(f"重試 {attempts} 次仍無法從後台取得影城主檔：{last_exc}")
    return payload


def load_runtime_master() -> tuple[dict, str]:
    if control_data.CINEMA_MASTER_PATH.exists():
        canonical = control_data.load_cinema_master()
        return control_data.active_cinema_payload(canonical), "git"
    return _fetch_legacy_master(), "backend"


def main() -> None:
    parser = argparse.ArgumentParser(description="建立爬蟲用影城主檔 SQLite。")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="目標 SQLite 路徑。")
    parser.add_argument(
        "--require-codes",
        action="store_true",
        help="要求至少一個據點有 source_location_code，否則直接失敗。",
    )
    args = parser.parse_args()

    try:
        payload, source = load_runtime_master()
    except Exception as exc:
        print(f"[錯誤] 無法建立影城主檔：{type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    chains = payload.get("chains", [])
    locations = payload.get("locations", [])
    if not chains or not locations:
        print(
            f"[錯誤] 影城主檔為空（品牌={len(chains)} 據點={len(locations)}）。",
            file=sys.stderr,
        )
        sys.exit(1)

    with_codes = sum(1 for loc in locations if (loc.get("source_location_code") or "").strip())
    if args.require_codes and with_codes == 0:
        print("[錯誤] 據點皆無 source_location_code，拒絕啟動爬蟲。", file=sys.stderr)
        sys.exit(1)

    n_chains, n_locations = rebuild_master(args.db, payload)
    print(
        f"[影城主檔] source={source} → {args.db}："
        f"品牌={n_chains}、據點={n_locations}（含代碼 {with_codes}）"
    )


if __name__ == "__main__":
    main()
