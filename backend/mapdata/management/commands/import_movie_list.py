"""import_movie_list：讀《電影清單.txt》一鍵匯入 / 更新 TrackedMovie。

這是 Phase 3 的開帳工具：把現有的《電影清單.txt》內容匯進追蹤片單資料表，
讓後台立刻有資料可管理。解析規則與 scripts/update_map.py 相容：
- 以 utf-8-sig 讀取；
- 去掉開頭編號（如「1. 」「2) 」「3、」）；
- 略過空行與以「#」開頭的註解行；
- 去重（同一次匯入中重複片名只取第一次）。

以 title 為鍵 get_or_create：新建者 is_active=True、sort_order 依檔案行序遞增
（10, 20, 30…）；已存在者僅更新 sort_order（不覆蓋 is_active，尊重後台的啟用狀態）。
idempotent：可重複執行。

用法：
    python manage.py import_movie_list           # 實際寫入 DB
    python manage.py import_movie_list --dry-run  # 只預覽，不寫 DB
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from mapdata.models import TrackedMovie

MOVIE_LIST_PATH = Path(settings.PROJECT_ROOT) / "電影清單.txt"
# 與 scripts/update_map.py 相同的開頭編號移除規則。
NUMBER_PREFIX_RE = re.compile(r"^\s*\d+\s*[.)、]\s*")


def read_movie_titles(path: Path) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        title = NUMBER_PREFIX_RE.sub("", raw_line).strip()
        if not title or title.startswith("#"):
            continue
        if title not in seen:
            titles.append(title)
            seen.add(title)
    return titles


class Command(BaseCommand):
    help = "從《電影清單.txt》匯入 / 更新 TrackedMovie（可重複執行）。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只預覽將建立/更新哪些片名，不實際寫入資料庫。",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if not MOVIE_LIST_PATH.exists():
            self.stdout.write(
                self.style.ERROR(f"找不到清單檔：{MOVIE_LIST_PATH}")
            )
            return

        titles = read_movie_titles(MOVIE_LIST_PATH)
        if not titles:
            self.stdout.write(self.style.WARNING("清單檔沒有可匯入的片名。"))
            return

        created = updated = 0
        for index, title in enumerate(titles, start=1):
            sort_order = index * 10
            existing = TrackedMovie.objects.filter(title=title).first()
            if existing is None:
                created += 1
                if dry_run:
                    self.stdout.write(f"[dry-run] 新建：{title}（排序 {sort_order}）")
                else:
                    TrackedMovie.objects.create(
                        title=title, is_active=True, sort_order=sort_order
                    )
            else:
                updated += 1
                if dry_run:
                    self.stdout.write(
                        f"[dry-run] 更新排序：{title} → {sort_order}"
                    )
                else:
                    existing.sort_order = sort_order
                    existing.save(update_fields=["sort_order", "updated_at"])

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}完成：新建 {created} 部、更新 {updated} 部（共 {len(titles)} 部）。"
            )
        )
