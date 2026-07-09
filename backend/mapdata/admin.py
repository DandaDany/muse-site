"""mapdata 後台設定。

資料分兩種性質：
1. 人工權威資料（CinemaChain, CinemaLocation, Movie, MovieTarget）：可在後台編輯。
2. 爬蟲產出（Showtime, CrawlRun, RawPage, KmlExport）：後台原則上唯讀，
   僅供人查閱，不手動修改，避免與爬蟲流程衝突。
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    CinemaChain,
    CinemaLocation,
    CrawlRun,
    KmlExport,
    Movie,
    MovieTarget,
    RawPage,
    Showtime,
)


class ReadOnlyAdminMixin:
    """唯讀 ModelAdmin 混入類別。

    用於爬蟲產出的資料表：關閉新增／修改／刪除，只保留查閱。
    """

    def has_add_permission(self, request):  # noqa: D401
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# 人工權威資料（可編輯）
# ---------------------------------------------------------------------------
@admin.register(CinemaChain)
class CinemaChainAdmin(admin.ModelAdmin):
    """影城品牌。被 CinemaLocation / MovieTarget 以 autocomplete 參照，故需 search_fields。"""

    list_display = (
        "chain_name",
        "official_url",
        "all_locations_assumed_showing",
        "active",
    )
    list_filter = ("active", "all_locations_assumed_showing")
    search_fields = ("chain_name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(CinemaLocation)
class CinemaLocationAdmin(admin.ModelAdmin):
    """影城據點。被 MovieTarget / Showtime 參照，需 search_fields 供 autocomplete。"""

    list_display = (
        "location_name",
        "chain",
        "city",
        "address",
        "latitude",
        "longitude",
        "active",
    )
    list_filter = ("active", "city", "chain")
    search_fields = ("location_name", "address", "city")
    autocomplete_fields = ("chain",)
    list_select_related = ("chain",)
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 50


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    """電影。被 MovieTarget / Showtime / CrawlRun / KmlExport 參照，需 search_fields。"""

    list_display = ("title", "original_title", "release_date", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("title", "original_title")
    readonly_fields = ("created_at", "updated_at")


@admin.register(MovieTarget)
class MovieTargetAdmin(admin.ModelAdmin):
    """追蹤目標：某電影要在哪些品牌／據點追場次。"""

    list_display = ("movie", "chain", "location", "target_scope", "status")
    list_filter = ("target_scope", "status")
    search_fields = ("movie__title", "chain__chain_name", "location__location_name")
    autocomplete_fields = ("movie", "chain", "location")
    list_select_related = ("movie", "chain", "location")
    readonly_fields = ("created_at", "updated_at")


# ---------------------------------------------------------------------------
# 爬蟲產出（唯讀）
# ---------------------------------------------------------------------------
@admin.register(Showtime)
class ShowtimeAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """場次：爬蟲產出，純查閱。"""

    list_display = (
        "movie",
        "location",
        "show_date",
        "start_time",
        "format",
        "language",
        "auditorium",
    )
    # 跨表過濾：電影 / 日期 / 品牌 / 縣市，另加放映格式與語言。
    #   品牌 location__chain、縣市 location__city 皆為關聯欄位，
    #   Django admin 的 list_filter 支援以雙底線跨關聯過濾。
    list_filter = (
        "movie",
        "show_date",
        "location__chain",
        "location__city",
        "format",
        "language",
    )
    search_fields = ("movie__title", "location__location_name", "location__city")
    # 註：show_date 等日期欄位在 model 中為 CharField（非 DateField），
    #     不能使用 date_hierarchy，否則會觸發 admin 系統檢查錯誤。
    # 一併預抓 location__chain，避免品牌欄位造成 N+1 查詢。
    list_select_related = ("movie", "location", "location__chain")
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 50


@admin.register(CrawlRun)
class CrawlRunAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """爬蟲執行紀錄：用來回答「今天哪些來源成功／失敗」。"""

    # 各狀態對應的背景色，供 status_badge 使用
    _STATUS_COLORS = {
        "success": "#2e7d32",  # 綠：成功
        "failed": "#c62828",   # 紅：失敗
        "partial": "#ef6c00",  # 橘：部分成功
        "running": "#616161",  # 灰：執行中
    }

    def status_badge(self, obj):
        """以帶背景色的小標籤呈現狀態，讓列表一眼看出成功／失敗。"""
        color = self._STATUS_COLORS.get(obj.status, "#616161")
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
            'background:{};color:#fff;font-size:12px;white-space:nowrap;">{}</span>',
            color,
            obj.status or "-",
        )

    status_badge.short_description = "狀態"

    list_display = (
        "source_name",
        "movie",
        "run_type",
        "status_badge",
        "rows_found",
        "rows_saved",
        "started_at",
        "finished_at",
    )
    list_filter = ("status", "run_type", "source_name", "started_at")
    search_fields = ("source_name", "error_message")
    # 註：started_at 為 CharField，故不使用 date_hierarchy。
    list_select_related = ("movie",)
    list_per_page = 50


@admin.register(RawPage)
class RawPageAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """原始頁面快照：爬蟲抓回的原始 HTML／資料，純查閱。"""

    list_display = (
        "source_url",
        "crawl_run",
        "http_status",
        "content_sha256",
        "local_path",
        "fetched_at",
    )
    list_filter = ("http_status", "fetched_at")
    search_fields = ("source_url", "content_sha256")
    # 註：fetched_at 為 CharField，故不使用 date_hierarchy。
    list_select_related = ("crawl_run",)


@admin.register(KmlExport)
class KmlExportAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """KML 匯出紀錄：地圖輸出檔，純查閱。"""

    list_display = ("movie", "export_date", "file_path", "placemark_count", "created_at")
    list_filter = ("export_date",)
    search_fields = ("movie__title", "file_path")
    # 註：export_date 為 CharField，故不使用 date_hierarchy。
    list_select_related = ("movie",)


# ---------------------------------------------------------------------------
# 後台標題
# ---------------------------------------------------------------------------
admin.site.site_header = "muse-site 影城地圖後台"
admin.site.site_title = "muse-site 後台"
admin.site.index_title = "資料管理"
# 右上「查看網站」連到營運儀表板（由另一位同事建立於 /dashboard/）
admin.site.site_url = "/dashboard/"
