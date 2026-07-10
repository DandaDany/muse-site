"""export_movie_list：把啟用中的追蹤電影寫回專案根的《電影清單.txt》。

這是 Phase 3 的相容匯出：TrackedMovie 已成為追蹤電影的真相來源，但現有爬蟲
（scripts/update_map.py 等）仍讀《電影清單.txt》。本指令把 is_active=True 的
追蹤電影，依 sort_order/title 排序寫回 txt，格式與現有解析器相容（每行「N. 片名」，
utf-8-sig）。

覆寫前會自動備份舊檔到 data/backup/movie_title_YYYYMMDD_HHMMSS.txt。

別名（aliases）為 DB-only，不寫進 txt（現有 txt 只有片名；別名供日後場次比對）。

用法：
    python manage.py export_movie_list           # 實際寫入（含備份）
    python manage.py export_movie_list --dry-run  # 只預覽，不寫檔
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from mapdata.models import TrackedMovie

MOVIE_LIST_PATH = Path(settings.PROJECT_ROOT) / "電影清單.txt"
BACKUP_DIR = Path(settings.PROJECT_ROOT) / "data" / "backup"


class Command(BaseCommand):
    help = "把啟用中的追蹤電影匯出回《電影清單.txt》（覆寫前自動備份）。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只預覽將寫入的內容與備份路徑，不實際寫檔。",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        movies = list(
            TrackedMovie.objects.filter(is_active=True).order_by("sort_order", "title")
        )
        lines = [f"{i}. {m.title}" for i, m in enumerate(movies, start=1)]
        content = "\n".join(lines) + ("\n" if lines else "")

        if dry_run:
            self.stdout.write(self.style.WARNING("[dry-run] 將寫入以下內容："))
            self.stdout.write(content or "（無啟用中的追蹤電影）")
            if MOVIE_LIST_PATH.exists():
                self.stdout.write(
                    f"[dry-run] 會先備份現有檔到 {BACKUP_DIR}/movie_title_*.txt"
                )
            self.stdout.write(f"[dry-run] 目標檔：{MOVIE_LIST_PATH}")
            return

        # 覆寫前備份既有檔。
        if MOVIE_LIST_PATH.exists():
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = BACKUP_DIR / f"movie_title_{stamp}.txt"
            shutil.copy2(MOVIE_LIST_PATH, backup_path)
            self.stdout.write(f"已備份舊檔到：{backup_path}")

        MOVIE_LIST_PATH.write_text(content, encoding="utf-8-sig")
        self.stdout.write(
            self.style.SUCCESS(
                f"已匯出 {len(movies)} 部啟用中的追蹤電影到 {MOVIE_LIST_PATH}。"
            )
        )
