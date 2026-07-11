"""mapdata 後台設定。

資料分兩種性質：
1. 人工權威資料（CinemaChain, CinemaLocation, TrackedMovie）：可在後台編輯。
   （Movie 由爬蟲維護、於選單隱藏；MovieTarget 已從後台移除。）
2. 爬蟲產出（Showtime, CrawlRun, RawPage, KmlExport）：後台原則上唯讀，
   僅供人查閱，不手動修改，避免與爬蟲流程衝突。
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    CinemaChain,
    CinemaLocation,
    CrawlReport,
    CrawlRun,
    KmlExport,
    Movie,
    RawPage,
    Showtime,
    TrackedMovie,
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
    """電影（爬蟲自動產生的主檔，場次掛在其下）。

    刻意從後台選單隱藏（get_model_perms 回傳空 dict）：使用者只需操作「追蹤電影」，
    這張表由爬蟲維護、不需人工編輯。仍保留登錄與 search_fields，供程式與
    autocomplete 使用。
    """

    list_display = ("title", "original_title", "release_date", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("title", "original_title")
    readonly_fields = ("created_at", "updated_at")

    def get_model_perms(self, request):
        # 回傳空權限 → 不出現在後台首頁選單（但仍可被 autocomplete/程式使用）。
        return {}


@admin.register(TrackedMovie)
class TrackedMovieAdmin(admin.ModelAdmin):
    """追蹤片單：人工維護的可編輯資料表（非唯讀）。

    稽核欄位（created_by / created_at / updated_by / updated_at）不可手改，
    改由 save_model 自動填入。
    """

    list_display = (
        "title",
        "target_date",
        "collect_status",
        "is_active",
        "sort_order",
        "updated_by",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("title", "aliases")
    # 允許直接在列表頁調整啟用狀態與排序。
    list_editable = ("is_active", "sort_order")
    ordering = ("sort_order", "title")
    # 稽核欄位唯讀，由 save_model 自動維護。
    readonly_fields = ("created_by", "created_at", "updated_by", "updated_at")

    @admin.display(description="收集狀態")
    def collect_status(self, obj):
        """依上映日期 vs 台北今天，顯示這部是否會被爬蟲收集。"""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Asia/Taipei")).date()
        if not obj.is_active:
            return format_html('<span style="color:#8a8a8a">已停用</span>')
        if obj.target_date and obj.target_date > today:
            return format_html('<span style="color:#b26a00">未上映 · 跳過</span>')
        return format_html('<span style="color:#1a7f37">上映中 · 收集</span>')

    def save_model(self, request, obj, form, change):
        """自動填入稽核欄位：新建時記錄建立者，每次儲存都記錄更新者。"""
        if not change or obj.pk is None:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


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


@admin.register(CrawlReport)
class CrawlReportAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """執行報告：本機每日執行的摘要（由 API 回傳），純查閱。"""

    list_display = (
        "run_id",
        "show_date",
        "status",
        "sources_success",
        "sources_failed",
        "showtimes_saved",
        "git_push_status",
        "worker_name",
        "created_at",
    )
    list_filter = ("status", "show_date", "git_push_status", "movie_list_source")
    search_fields = ("run_id", "worker_name", "commit_sha")


# ---------------------------------------------------------------------------
# 後台標題
# ---------------------------------------------------------------------------
admin.site.site_header = "muse-site 影城地圖後台"
admin.site.site_title = "muse-site 後台"
admin.site.index_title = "資料管理"
# 右上「查看網站」連到營運儀表板（由另一位同事建立於 /dashboard/）
admin.site.site_url = "/dashboard/"
