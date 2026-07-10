"""import_from_sqlite：把本機 SQLite 的人工資料匯入目前資料庫（含雲端 Postgres）。

用途：上線後雲端 Postgres 是空的，用這支指令把本機 data/movie_map.sqlite 的
「人工權威資料」灌進去，讓線上後台/地圖有真實資料。

匯入範圍（預設）：cinema_chains、cinema_locations、movies、movie_targets
（這些是人工維護的資料）。場次 showtimes 屬爬蟲產出、量大且會被重爬覆蓋，
預設不匯入；需要時加 --with-showtimes。

以「自然鍵」upsert，因此可重複執行（idempotent），且來源與目的地的 id 不同也沒關係：
- 品牌：chain_name
- 據點：(所屬品牌, location_name)
- 電影：(title, release_date)
- 追蹤目標：(movie, chain, location)

典型用法（在本機把資料推上雲端 Postgres）：
    # DATABASE_URL 指向 Render 的外部連線字串
    DATABASE_URL="postgres://...":  python manage.py import_from_sqlite ../data/movie_map.sqlite
或先預覽：
    python manage.py import_from_sqlite ../data/movie_map.sqlite --dry-run
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mapdata.models import (
    CinemaChain,
    CinemaLocation,
    Movie,
    MovieTarget,
    Showtime,
)

DEFAULT_SOURCE = Path(settings.PROJECT_ROOT) / "data" / "movie_map.sqlite"


class Command(BaseCommand):
    help = "把本機 SQLite 的人工資料（品牌/據點/電影/追蹤目標）匯入目前資料庫。"

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            nargs="?",
            default=str(DEFAULT_SOURCE),
            help="來源 SQLite 檔路徑（預設 data/movie_map.sqlite）。",
        )
        parser.add_argument(
            "--with-showtimes",
            action="store_true",
            help="一併匯入場次（預設不匯入；場次通常由爬蟲重新產生）。",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只統計將匯入的筆數，不寫入資料庫。",
        )

    def handle(self, *args, **options):
        source = Path(options["source"])
        if not source.exists():
            raise CommandError(f"找不到來源 SQLite：{source}")

        dry_run = options["dry_run"]
        with_showtimes = options["with_showtimes"]

        conn = sqlite3.connect(str(source))
        conn.row_factory = sqlite3.Row

        stats = {}
        try:
            with transaction.atomic():
                chain_map = self._import_chains(conn, stats)
                location_map = self._import_locations(conn, chain_map, stats)
                movie_map = self._import_movies(conn, stats)
                self._import_movie_targets(
                    conn, movie_map, chain_map, location_map, stats
                )
                if with_showtimes:
                    self._import_showtimes(
                        conn, movie_map, location_map, stats
                    )
                if dry_run:
                    transaction.set_rollback(True)
        finally:
            conn.close()

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}匯入完成："))
        for key, (created, updated) in stats.items():
            self.stdout.write(f"  {key}: 新建 {created} / 更新 {updated}")

    # --- 各表匯入 -----------------------------------------------------------

    def _rows(self, conn, table):
        try:
            return conn.execute(f"SELECT * FROM {table}").fetchall()
        except sqlite3.OperationalError:
            return []

    @staticmethod
    def _now():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _ts_defaults(self, row):
        """建立時的時間戳預設值。

        既有 SQLite 業務表的 created_at/updated_at 為 NOT NULL，而 Django model 把
        它們宣告為可空 CharField。若不在 INSERT 當下給值，會違反 NOT NULL。這裡從
        來源列複製（沒有就用現在時間），確保建立成功並保留原始時間。
        """
        now = self._now()
        keys = row.keys()
        return {
            "created_at": (row["created_at"] if "created_at" in keys else None) or now,
            "updated_at": (row["updated_at"] if "updated_at" in keys else None) or now,
        }

    def _import_chains(self, conn, stats):
        created = updated = 0
        id_map = {}
        for row in self._rows(conn, "cinema_chains"):
            obj, is_new = CinemaChain.objects.get_or_create(
                chain_name=row["chain_name"],
                defaults=self._ts_defaults(row),
            )
            obj.official_url = row["official_url"]
            obj.crawl_url = row["crawl_url"]
            obj.booking_url = row["booking_url"]
            obj.all_locations_assumed_showing = bool(
                row["all_locations_assumed_showing"]
            )
            obj.notes = row["notes"]
            obj.active = bool(row["active"])
            obj.save()
            id_map[row["id"]] = obj
            created, updated = (created + 1, updated) if is_new else (created, updated + 1)
        stats["影城品牌"] = (created, updated)
        return id_map

    def _import_locations(self, conn, chain_map, stats):
        created = updated = 0
        id_map = {}
        for row in self._rows(conn, "cinema_locations"):
            chain = chain_map.get(row["chain_id"])
            if chain is None:
                continue
            obj, is_new = CinemaLocation.objects.get_or_create(
                chain=chain, location_name=row["location_name"],
                defaults=self._ts_defaults(row),
            )
            obj.display_name = row["display_name"]
            obj.address = row["address"]
            obj.city = row["city"]
            obj.district = row["district"]
            obj.latitude = row["latitude"]
            obj.longitude = row["longitude"]
            obj.source_location_code = row["source_location_code"]
            obj.location_url = row["location_url"]
            obj.source_url = row["source_url"]
            obj.notes = row["notes"]
            obj.active = bool(row["active"])
            obj.save()
            id_map[row["id"]] = obj
            created, updated = (created + 1, updated) if is_new else (created, updated + 1)
        stats["影城據點"] = (created, updated)
        return id_map

    def _import_movies(self, conn, stats):
        created = updated = 0
        id_map = {}
        for row in self._rows(conn, "movies"):
            obj, is_new = Movie.objects.get_or_create(
                title=row["title"], release_date=row["release_date"],
                defaults=self._ts_defaults(row),
            )
            obj.original_title = row["original_title"]
            obj.notes = row["notes"]
            obj.active = bool(row["active"])
            obj.save()
            id_map[row["id"]] = obj
            created, updated = (created + 1, updated) if is_new else (created, updated + 1)
        stats["電影"] = (created, updated)
        return id_map

    def _import_movie_targets(self, conn, movie_map, chain_map, location_map, stats):
        created = updated = 0
        for row in self._rows(conn, "movie_targets"):
            movie = movie_map.get(row["movie_id"])
            chain = chain_map.get(row["chain_id"])
            if movie is None or chain is None:
                continue
            location = location_map.get(row["location_id"]) if row["location_id"] else None
            obj, is_new = MovieTarget.objects.get_or_create(
                movie=movie, chain=chain, location=location,
                defaults={
                    # target_scope / status 有 NOT NULL + CHECK 限制，
                    # 必須在 INSERT 當下就給來源的合法值（否則會用 model 空預設觸發 CHECK 失敗）。
                    **self._ts_defaults(row),
                    "target_scope": row["target_scope"],
                    "status": row["status"],
                },
            )
            obj.target_scope = row["target_scope"]
            obj.status = row["status"]
            obj.notes = row["notes"]
            obj.save()
            created, updated = (created + 1, updated) if is_new else (created, updated + 1)
        stats["追蹤目標"] = (created, updated)

    def _import_showtimes(self, conn, movie_map, location_map, stats):
        created = updated = 0
        for row in self._rows(conn, "showtimes"):
            movie = movie_map.get(row["movie_id"])
            location = location_map.get(row["location_id"])
            if movie is None or location is None:
                continue
            obj, is_new = Showtime.objects.get_or_create(
                movie=movie,
                location=location,
                show_date=row["show_date"],
                start_time=row["start_time"],
                format=row["format"],
                language=row["language"],
                subtitle=row["subtitle"],
                booking_url=row["booking_url"],
                defaults=self._ts_defaults(row),
            )
            obj.end_time = row["end_time"]
            obj.auditorium = row["auditorium"]
            obj.source_url = row["source_url"]
            obj.raw_text = row["raw_text"]
            obj.save()
            created, updated = (created + 1, updated) if is_new else (created, updated + 1)
        stats["場次"] = (created, updated)
