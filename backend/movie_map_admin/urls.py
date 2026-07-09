"""
movie_map_admin 專案的最上層 URL 設定。

路由總覽：
- /admin/    Django 內建管理後台（登入、編輯影城/電影、查爬蟲紀錄等由別的模組負責）
- /          直接導向 /admin/，方便使用者一進站就能登入後台
- /healthz/  健康檢查端點，供雲端平台（例如 Render / Railway / GCP）探測服務存活狀態
"""

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import path
from django.views.generic import RedirectView


def healthz(request: HttpRequest) -> HttpResponse:
    """雲端健康檢查用：只要能回應 200 就代表服務正常存活，不觸碰資料庫。"""
    return HttpResponse("ok")


urlpatterns = [
    path("admin/", admin.site.urls),
    # 根路徑直接導向後台登入頁，方便使用者操作
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
    path("healthz/", healthz),
]
