"""
movie_map_admin 專案的最上層 URL 設定。

路由總覽：
- /admin/     Django 內建管理後台（登入、編輯影城/電影、查爬蟲紀錄等由別的模組負責）
- /dashboard/ 營運儀表板，顯示今日爬蟲成功/失敗、場次統計等總覽資訊
- /           直接導向 /dashboard/，方便使用者一進站就能看到營運總覽
              （dashboard view 本身已用 staff_member_required 保護，未登入
              會自動被導去 /admin/ 的登入頁，不需要在這裡另外處理）
- /healthz/   健康檢查端點，供雲端平台（例如 Render / Railway / GCP）探測服務存活狀態
"""

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import path
from django.views.generic import RedirectView

from mapdata.views import dashboard


def healthz(request: HttpRequest) -> HttpResponse:
    """雲端健康檢查用：只要能回應 200 就代表服務正常存活，不觸碰資料庫。"""
    return HttpResponse("ok")


urlpatterns = [
    path("admin/", admin.site.urls),
    # 營運儀表板：今日各爬蟲來源成功/失敗、場次統計等總覽（見 mapdata.views.dashboard）
    path("dashboard/", dashboard, name="dashboard"),
    # 根路徑改導向營運儀表板，方便使用者一進站就能掌握營運狀況
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
    path("healthz/", healthz),
]
