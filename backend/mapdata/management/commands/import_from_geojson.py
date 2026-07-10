"""import_from_geojson：從 web/data/locations.geojson 匯入影城品牌與據點。

用途：不需要本機 SQLite，直接用 repo 內已發佈的地圖資料（含真實影城名稱、
地址、縣市、經緯度、官網）把「影城主檔」灌進目前資料庫。特別適合雲端 Postgres
初次開帳——因為 geojson 已隨程式部署到 Render，可在 build 階段直接匯入。

只匯入 curated（人工權威）資料：cinema_chains、cinema_locations。
不匯入場次（geojson 內的場次是某天的快照，場次應由本機爬蟲產生）。

以自然鍵 upsert（品牌 chain_name、據點 (品牌, location_name)），可重複執行。

用法：
    python manage.py import_from_geojson            # 匯入
    python manage.py import_from_geojson --dry-run  # 只預覽
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mapdata.models import CinemaChain, CinemaLocation

DEFAULT_GEOJSON = Path(settings.PROJECT_ROOT) / "web" / "data" / "locations.geojson"


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _collect_features(data) -> list:
    """蒐集所有不重複的據點 feature（跨 top-level 與各電影 movie_features）。"""
    seen = set()
    result = []
    buckets = [data.get("features", [])]
    for feats in (data.get("movie_features") or {}).values():
        buckets.append(feats)
    for feats in buckets:
        for f in feats or []:
            p = f.get("properties", {})
            key = (p.get("chain_name"), p.get("location_name"))
            if key in seen or not p.get("chain_name") or not p.get("location_name"):
                continue
            seen.add(key)
            result.append(f)
    return result


class Command(BaseCommand):
    help = "從 web/data/locations.geojson 匯入影城品牌與據點（不含場次）。"

    def add_arguments(self, parser):
        parser.add_argument("geojson", nargs="?", default=str(DEFAULT_GEOJSON))
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["geojson"])
        if not path.exists():
            raise CommandError(f"找不到 geojson：{path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        features = _collect_features(data)

        chains_created = chains_updated = 0
        locs_created = locs_updated = 0

        with transaction.atomic():
            chain_cache: dict[str, CinemaChain] = {}
            for f in features:
                p = f["properties"]
                coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
                lng, lat = coords[0], coords[1]
                chain_name = p["chain_name"]
                loc_name = p["location_name"]

                chain = chain_cache.get(chain_name)
                if chain is None:
                    chain, is_new = CinemaChain.objects.get_or_create(
                        chain_name=chain_name,
                        defaults={"created_at": _now(), "updated_at": _now()},
                    )
                    chain_cache[chain_name] = chain
                    chains_created += int(is_new)
                    chains_updated += int(not is_new)
                    # 補官網/爬蟲來源（若 geojson 有提供）
                    changed = False
                    if p.get("official_url") and not chain.official_url:
                        chain.official_url = p["official_url"]; changed = True
                    if p.get("crawl_url") and not chain.crawl_url:
                        chain.crawl_url = p["crawl_url"]; changed = True
                    if changed and not options["dry_run"]:
                        chain.save()

                loc, is_new = CinemaLocation.objects.get_or_create(
                    chain=chain, location_name=loc_name,
                    defaults={"created_at": _now(), "updated_at": _now()},
                )
                locs_created += int(is_new)
                locs_updated += int(not is_new)
                loc.address = p.get("address")
                loc.city = p.get("city")
                loc.latitude = lat
                loc.longitude = lng
                loc.location_url = p.get("location_url")
                if not options["dry_run"]:
                    loc.save()

            if options["dry_run"]:
                transaction.set_rollback(True)

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}影城品牌：新建 {chains_created} / 既有 {chains_updated}；"
            f"影城據點：新建 {locs_created} / 更新 {locs_updated}"
        ))
