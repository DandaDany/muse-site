"""seed_roles：建立「管理員」與「編輯者」兩個群組並指派權限。

權限矩陣（來自架構設計書）：

- 管理員：mapdata 所有 model 的 add/change/delete/view，
  另加 auth.User 的 add/change/delete/view（可管理使用者）。
- 編輯者：
  - 人工權威資料（CinemaChain / CinemaLocation / Movie / MovieTarget）：
    view/add/change（不給 delete）。
  - 爬蟲產出（Showtime / CrawlRun / RawPage / KmlExport）：只有 view。
  - 不可管理使用者。

本指令為 idempotent（可重複執行）：每次都先 clear 再重新指派。
"""

from django.apps import apps as django_apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

# mapdata 的 model（以 model_name 小寫表示，用於組出 codename）
# 人工權威資料：可編輯（trackedmovie 為 Phase 3 新增的追蹤片單 managed 表）
EDITABLE_MODELS = ["cinemachain", "cinemalocation", "movie", "movietarget", "trackedmovie"]
# 爬蟲產出：後台唯讀
READONLY_MODELS = ["showtime", "crawlrun", "rawpage", "kmlexport"]
ALL_MAPDATA_MODELS = EDITABLE_MODELS + READONLY_MODELS


class Command(BaseCommand):
    help = "建立/更新『管理員』與『編輯者』群組並依權限矩陣指派權限（可重複執行）。"

    def handle(self, *args, **options):
        # 1) 確保 permissions 已建立。
        #    全新 DB 於 migrate 後、post_migrate signal 可能尚未替所有 app 建好
        #    Permission，這裡主動補建，避免後續 Permission.objects.get(...) 抓不到。
        for app_config in django_apps.get_app_configs():
            create_permissions(app_config, verbosity=0)

        # 2) 建立兩個群組（idempotent）。
        admin_group, _ = Group.objects.get_or_create(name="管理員")
        editor_group, _ = Group.objects.get_or_create(name="編輯者")

        # 3) 依權限矩陣組出各群組要指派的 codename 清單。
        #    管理員：mapdata 全部 CRUD + auth.User 全部 CRUD。
        admin_codenames = []
        for model in ALL_MAPDATA_MODELS:
            for action in ("add", "change", "delete", "view"):
                admin_codenames.append(f"{action}_{model}")
        # 管理員可管理使用者（auth.User）。
        user_codenames = [f"{action}_user" for action in ("add", "change", "delete", "view")]
        admin_codenames.extend(user_codenames)

        #    編輯者：可編輯資料給 view/add/change（不給 delete）；唯讀資料只給 view。
        editor_codenames = []
        for model in EDITABLE_MODELS:
            for action in ("view", "add", "change"):
                editor_codenames.append(f"{action}_{model}")
        for model in READONLY_MODELS:
            editor_codenames.append(f"view_{model}")

        # 4) 依 codename 取出 Permission 物件並指派（先 clear 再 set，確保可重複執行）。
        admin_perms = self._get_permissions(admin_codenames)
        editor_perms = self._get_permissions(editor_codenames)

        admin_group.permissions.clear()
        admin_group.permissions.set(admin_perms)

        editor_group.permissions.clear()
        editor_group.permissions.set(editor_perms)

        # 5) 輸出結果。
        self.stdout.write(
            self.style.SUCCESS(
                f"『管理員』已指派 {len(admin_perms)} 個權限。"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"『編輯者』已指派 {len(editor_perms)} 個權限。"
            )
        )

    def _get_permissions(self, codenames):
        """依 codename 清單取出對應的 Permission 物件。

        mapdata 的 codename 與 auth.User 的 *_user 皆為唯一，故直接以 codename 查詢即可。
        若清單中某 codename 查不到會拋出例外，方便及早發現 model／權限設定問題。
        """
        perms = []
        for codename in codenames:
            perm = Permission.objects.get(codename=codename)
            perms.append(perm)
        return perms
