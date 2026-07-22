"""把本機 SQLite 裡「即時爬到的據點代碼」回寫到後台，持久化為單一來源。

背景：新光/in89/國賓 的 source_location_code 是每次排程即時爬官網取得，原本只留在
當次執行的暫存 SQLite、沒存回後台。導致後台看不到這些代碼，且哪次官網逾時（如新光）
就整家沒資料、沒有備援。

本腳本在「即時爬代碼」之後執行：讀出 SQLite 內所有帶 source_location_code 的據點，
POST 到後台 /api/cinema-master/。後台以 (品牌, 據點名) 更新既有據點的代碼（找不到就
略過，不新建）。之後即使某天官網逾時，後台已有上次存好的代碼可用。

設定：MUSE_API_BASE_URL / MUSE_API_TOKEN（見 scripts/muse_api.py）。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    locations = collect_coded_locations(DEFAULT_DB_PATH)
    if not locations:
        print("[回寫代碼] 本機無帶代碼的據點，略過。")
        return
    try:
        resp = muse_api.push_cinema_codes(locations)
    except Exception as exc:
        # 容錯：回寫失敗不應中斷排程（下次成功爬取時會再回寫）。
        print(f"[回寫代碼] 失敗（不中斷）：{type(exc).__name__}: {exc}", file=sys.stderr)
        return
    print(f"[回寫代碼] 送出 {len(locations)} 筆 → "
          f"後台更新 {resp.get('updated')}、未變 {resp.get('unchanged')}、"
          f"略過 {resp.get('skipped')}")


if __name__ == "__main__":
    main()
