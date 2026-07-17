"""從雲端後台拉影城主檔，建立本機爬蟲用的 SQLite。

用途：GitHub Actions 每次排程爬蟲前，在乾淨環境呼叫本腳本，向後台
`GET /api/cinema-master/` 取得影城品牌 + 據點（含爬蟲必需的
source_location_code），寫入 data/movie_map.sqlite 的 cinema_chains /
cinema_locations 兩張表。取代「把 binary SQLite 提交進 repo」的舊做法——
後台是影城主檔的單一真相來源（同片單 /api/tracked-movies/）。

設定：MUSE_API_BASE_URL / MUSE_API_TOKEN（見 scripts/muse_api.py）。
未設定或後台無資料時直接失敗，避免爬出空地圖。

注意：本腳本會「清掉並重建」cinema_chains / cinema_locations，設計給 CI 的
乾淨環境使用。若在本機執行，會以後台資料覆蓋這兩張表（不動場次）。
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
        # SQLite 的布林旗標以 0/1 儲存（schema 為 INTEGER）。
        if col in ("active", "all_locations_assumed_showing"):
            val = 1 if val else 0
        values.append(val)
    return tuple(values)


def rebuild_master(db_path: Path, payload: dict) -> tuple[int, int]:
    chains = payload["chains"]
    locations = payload["locations"]

    init_db(db_path)  # 確保 schema 存在（CREATE TABLE IF NOT EXISTS，冪等）
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")  # 重建期間先關 FK，避免清空順序限制
        # 只清影城主檔兩張；場次等爬蟲產出不動（CI 環境本就是空的）。
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="從後台拉影城主檔，建立本機爬蟲用的 SQLite。"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="目標 SQLite 路徑。")
    parser.add_argument(
        "--require-codes", action="store_true",
        help="要求至少一個據點有 source_location_code，否則視為後台未灌完整主檔而失敗。",
    )
    args = parser.parse_args()

    try:
        payload = muse_api.fetch_cinema_master()
    except Exception as exc:
        print(f"[錯誤] 無法從後台取得影城主檔：{exc}", file=sys.stderr)
        print("       請確認 GitHub Secrets 的 MUSE_API_BASE_URL / MUSE_API_TOKEN，"
              "以及後台已部署 /api/cinema-master/。", file=sys.stderr)
        sys.exit(1)

    chains = payload.get("chains", [])
    locations = payload.get("locations", [])
    if not chains or not locations:
        print(f"[錯誤] 後台影城主檔為空（品牌={len(chains)} 據點={len(locations)}）。"
              "請先對後台 Postgres 執行 import_from_sqlite 灌入影城資料。", file=sys.stderr)
        sys.exit(1)

    with_codes = sum(1 for loc in locations if (loc.get("source_location_code") or "").strip())
    if args.require_codes and with_codes == 0:
        print("[錯誤] 後台據點皆無 source_location_code，爬蟲將抓不到需代碼的來源（如威秀）。"
              "請確認後台是用 import_from_sqlite（含代碼）而非 import_from_geojson 灌入。",
              file=sys.stderr)
        sys.exit(1)

    n_chains, n_locations = rebuild_master(args.db, payload)
    print(f"[影城主檔] 已從後台重建 {args.db}："
          f"品牌={n_chains}、據點={n_locations}（其中含代碼 {with_codes}）")


if __name__ == "__main__":
    main()
