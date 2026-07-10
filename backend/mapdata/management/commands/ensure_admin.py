"""ensure_admin：依環境變數建立初始管理員帳號（部署用，冪等）。

在雲端部署時，用環境變數自動建立第一個可登入的超級使用者，並加入「管理員」
群組，免去 SSH 進去手動 createsuperuser。

讀取環境變數：
- DJANGO_SUPERUSER_USERNAME
- DJANGO_SUPERUSER_PASSWORD
- DJANGO_SUPERUSER_EMAIL（選填）

行為：
- 未設 USERNAME/PASSWORD：略過（不讓部署失敗）。
- 帳號已存在：確保 is_staff/is_superuser=True 並加入「管理員」群組，不覆寫密碼。
- 帳號不存在：建立超級使用者並加入「管理員」群組。

用法：python manage.py ensure_admin
"""

from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "依 DJANGO_SUPERUSER_* 環境變數建立/確保初始管理員帳號（冪等）。"

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")

        if not username or not password:
            self.stdout.write(
                "未設定 DJANGO_SUPERUSER_USERNAME / PASSWORD，略過建立管理員。"
            )
            return

        User = get_user_model()
        admin_group, _ = Group.objects.get_or_create(name="管理員")

        user = User.objects.filter(username=username).first()
        if user is None:
            user = User.objects.create_superuser(
                username=username, email=email, password=password
            )
            user.groups.add(admin_group)
            self.stdout.write(self.style.SUCCESS(f"已建立管理員帳號：{username}"))
        else:
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_staff", "is_superuser"])
            user.groups.add(admin_group)
            self.stdout.write(f"管理員帳號已存在，已確認權限：{username}")
