"""mapdata app 設定。"""

from django.apps import AppConfig


class MapdataConfig(AppConfig):
    """影城地圖資料 app：以 unmanaged models 唯讀對映現有 SQLite 的 8 張業務表。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "mapdata"
    verbose_name = "影城地圖資料"
