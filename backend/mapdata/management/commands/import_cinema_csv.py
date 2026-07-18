"""import_cinema_csv：把版控 CSV 的影城品牌/據點匯入目前資料庫（含雲端 Postgres）。

用途：讓影城代碼（source_location_code）等資料以「版控 CSV」為單一來源，於 Render
部署時自動同步進後台 Postgres，完全不需經本機 SQLite——支援「全雲端」運作。

以自然鍵 upsert，可重複執行（idempotent）：
- 品牌：chain_name
- 據點：(所屬品牌, location_name)

寫入策略（避免清掉後台管理員手動維護的資料）：
- source_location_code：CSV 有提供就以 CSV 為準寫入（版控代碼視為權威）。
- 其他欄位（地址/經緯度/各種 URL 等）：只有 CSV 該格「非空」時才覆寫，
  空白格不動後台既有值。

預設匯入 data/input 下含代碼的 CSV（威秀下拉代碼 + 手動補充 URL）。
典型用法：
    python manage.py import_cinema_csv                # 匯入預設 CSV 清單
    python manage.py import_cinema_csv path/a.csv b.csv --dry-run
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from mapdata.models import CinemaChain, CinemaLocation

DATA_INPUT = Path(settings.PROJECT_ROOT) / "data" / "input"
DEFAULT_CSVS = [
    DATA_INPUT / "vieshow_locations.csv",
    DATA_INPUT / "manual_location_urls.csv",
]

# CSV 表頭別名（對齊 scripts/import_cinema_sources.py 的欄位）。
ALIASES = {
    "chain_name": ["chain_name", "cinema_chain", "影城", "影城名稱"],
    "official_url": ["official_url", "url", "官方網址"],
    "crawl_url": ["crawl_url", "showtimes_url", "場次連結"],
    "booking_url": ["booking_url", "ticket_url", "訂票連結"],
    "all_locations_assumed_showing": ["all_locations_assumed_showing", "assume_all_locations"],
    "notes": ["notes", "備註"],
    "location_name": ["location_name", "branch_name", "據點", "分店名稱"],
    "address": ["address", "地址"],
    "city": ["city", "縣市", "城市"],
    "district": ["district", "行政區"],
    "latitude": ["latitude", "lat", "緯度"],
    "longitude": ["longitude", "lng", "lon", "經度"],
    "source_location_code": ["source_location_code", "theater_code", "cinema_code", "影城代碼"],
    "location_url": ["location_url", "branch_url", "分店連結"],
}


def _clean(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _pick(row: dict, field: str):
    for alias in ALIASES[field]:
        if alias in row:
            return _clean(row[alias])
    return None


def _as_bool(value, default=True):
    if value is None:
        return default
    return str(value).strip() not in ("0", "", "false", "False", "否", "N")


class Command(BaseCommand):
    help = "把版控 CSV 的影城品牌/據點（含 source_location_code）匯入目前資料庫。"

    def add_arguments(self, parser):
        parser.add_argument("csvs", nargs="*", help="CSV 路徑（可多個）；省略＝預設清單。")
        parser.add_argument("--dry-run", action="store_true", help="只統計、不寫入。")

    def handle(self, *args, **options):
        paths = [Path(p) for p in options["csvs"]] or DEFAULT_CSVS
        dry_run = options["dry_run"]

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chains_seen = 0
        loc_created = loc_updated = loc_coded = 0
        missing = []

        with transaction.atomic():
            for path in paths:
                if not path.exists():
                    missing.append(str(path))
                    continue
                with open(path, encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        chain_name = _pick(row, "chain_name")
                        location_name = _pick(row, "location_name")
                        if not chain_name or not location_name:
                            continue

                        chain, _ = CinemaChain.objects.get_or_create(
                            chain_name=chain_name,
                            defaults={"created_at": now, "updated_at": now},
                        )
                        # 品牌層級：非空才覆寫。
                        for attr in ("official_url", "crawl_url", "booking_url", "notes"):
                            val = _pick(row, attr)
                            if val is not None:
                                setattr(chain, attr, val)
                        assume = _pick(row, "all_locations_assumed_showing")
                        if assume is not None:
                            chain.all_locations_assumed_showing = _as_bool(assume)
                        chain.save()
                        chains_seen += 1

                        loc, created = CinemaLocation.objects.get_or_create(
                            chain=chain,
                            location_name=location_name,
                            defaults={"created_at": now, "updated_at": now},
                        )
                        # 代碼：CSV 有提供就以 CSV 為準（版控代碼權威）。
                        code = _pick(row, "source_location_code")
                        if code is not None:
                            loc.source_location_code = code
                            loc_coded += 1
                        # 其他欄位：只有非空才覆寫，不動後台既有的地址/經緯度。
                        for attr in ("display_name", "address", "city", "district",
                                     "location_url", "source_url", "notes"):
                            val = _pick(row, attr) if attr in ALIASES else None
                            if val is not None:
                                setattr(loc, attr, val)
                        for attr in ("latitude", "longitude"):
                            val = _pick(row, attr)
                            if val is not None:
                                try:
                                    setattr(loc, attr, float(val))
                                except ValueError:
                                    pass
                        loc.save()
                        loc_created += int(created)
                        loc_updated += int(not created)

            if dry_run:
                transaction.set_rollback(True)

        prefix = "[dry-run] " if dry_run else ""
        for m in missing:
            self.stdout.write(self.style.WARNING(f"跳過不存在的 CSV：{m}"))
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}匯入完成：據點 新建 {loc_created} / 更新 {loc_updated}；"
            f"寫入代碼 {loc_coded} 筆。"
        ))
