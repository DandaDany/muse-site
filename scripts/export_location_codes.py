"""把本機 SQLite 的據點代碼匯出成版控 CSV，供後台部署時灌入（免碰資料庫）。

用途：本機 data/movie_map.sqlite 已存有全部需代碼影城（威秀/新光/in89/國賓/百老匯/
秀泰/美麗新）的 source_location_code。跑這支把它們匯出成 data/input/cinema_codes.csv，
提交進版控後，後台 build.sh 的 import_cinema_csv 會在部署時把代碼灌進 Postgres，
讓雲端排程跟本機一樣完整——不需 DATABASE_URL、不需連資料庫。

用法：
    python scripts/export_location_codes.py
    git add data/input/cinema_codes.csv && git commit -m "data: 影城據點代碼" && git push
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_DIR / "data" / "movie_map.sqlite"
OUT_CSV = PROJECT_DIR / "data" / "input" / "cinema_codes.csv"


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"找不到本機主檔：{DB_PATH}")

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT cc.chain_name, cl.location_name, cl.source_location_code
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cl.source_location_code IS NOT NULL
          AND TRIM(cl.source_location_code) <> ''
        ORDER BY cc.chain_name, cl.location_name
        """
    ).fetchall()
    con.close()

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["chain_name", "location_name", "source_location_code"])
        for r in rows:
            writer.writerow([r["chain_name"], r["location_name"], r["source_location_code"]])

    from collections import Counter
    by_chain = Counter(r["chain_name"] for r in rows)
    print(f"匯出 {len(rows)} 筆代碼 → {OUT_CSV}")
    for chain, n in sorted(by_chain.items(), key=lambda x: -x[1]):
        print(f"  {n:3d}  {chain}")
    print("\n下一步：git add data/input/cinema_codes.csv && git commit -m 'data: 影城據點代碼' && git push")


if __name__ == "__main__":
    main()
