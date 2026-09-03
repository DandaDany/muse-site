"""Persist refreshed cinema source_location_code values.

After the GitHub control plane is materialized, codes are written back to
`data/control/cinema_master.json` by natural key. Before migration, the legacy
backend POST remains as a compatibility fallback.

Blank/missing runtime codes never erase a last-known-good canonical code.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import control_data  # noqa: E402
import muse_api  # noqa: E402
from init_db import DEFAULT_DB_PATH  # noqa: E402


def collect_coded_locations(db_path: Path) -> list[dict]:
    if not db_path.exists():
        return []
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
    return [
        {
            "chain_name": r["chain_name"],
            "location_name": r["location_name"],
            "source_location_code": r["source_location_code"],
        }
        for r in rows
    ]


def main() -> None:
    if control_data.CINEMA_MASTER_PATH.exists():
        try:
            updated, skipped = control_data.persist_codes_from_sqlite(
                DEFAULT_DB_PATH,
                control_data.CINEMA_MASTER_PATH,
            )
        except Exception as exc:
            # Canonical data exists: fail closed instead of silently reverting to Render.
            print(
                f"[回寫代碼] GitHub master 更新失敗：{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            raise
        print(f"[回寫代碼] GitHub master 更新 {updated}、略過 {skipped}")
        return

    locations = collect_coded_locations(DEFAULT_DB_PATH)
    if not locations:
        print("[回寫代碼] 本機無帶代碼的據點，略過。")
        return
    try:
        resp = muse_api.push_cinema_codes(locations)
    except Exception as exc:
        print(f"[回寫代碼] 後台回寫失敗（不中斷）：{type(exc).__name__}: {exc}", file=sys.stderr)
        return
    print(
        f"[回寫代碼] legacy backend：送出 {len(locations)} 筆 → "
        f"更新 {resp.get('updated')}、未變 {resp.get('unchanged')}、略過 {resp.get('skipped')}"
    )


if __name__ == "__main__":
    main()
