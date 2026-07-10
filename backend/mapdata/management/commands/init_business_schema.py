"""init_business_schema：在雲端 Postgres 建立 8 張業務表（部署用）。

背景：cinema_chains 等 8 張表在後台是 unmanaged models（managed=False），
Django migrate 不會建立它們。在全新的雲端 Postgres 上，必須執行
sql/schema_postgres.sql 先把這些表建好，/admin 的影城/場次頁才不會報錯。

行為：
- Postgres（connection.vendor == 'postgresql'）：執行 sql/schema_postgres.sql
  （全部 CREATE TABLE IF NOT EXISTS，可重複執行）。
- 其他（本機 SQLite）：跳過，因為那些表已由 scripts/init_db.py 依
  sql/schema.sql 建立。

用法：python manage.py init_business_schema
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

SCHEMA_PATH = Path(settings.PROJECT_ROOT) / "sql" / "schema_postgres.sql"


class Command(BaseCommand):
    help = "在 Postgres 上建立 8 張 unmanaged 業務表（SQLite 上為 no-op）。"

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write(
                f"目前資料庫為 {connection.vendor}，業務表應已由 sql/schema.sql 建立，跳過。"
            )
            return

        if not SCHEMA_PATH.exists():
            self.stdout.write(self.style.ERROR(f"找不到 schema 檔：{SCHEMA_PATH}"))
            return

        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with connection.cursor() as cursor:
            cursor.execute(sql)
        self.stdout.write(
            self.style.SUCCESS("已在 Postgres 建立/確認 8 張業務表（schema_postgres.sql）。")
        )
