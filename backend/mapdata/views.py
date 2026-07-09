"""
mapdata.views — 營運儀表板（Phase 2）

提供後台首頁等級的「一眼看懂今天狀況」頁面：
- 當日各爬蟲來源的執行狀況（成功／失敗／執行中、found/saved、錯誤摘要）
- 當日場次、影城、電影等 KPI 統計
- 上次爬蟲更新時間、前端 GeoJSON 檔案更新時間
- 快速連結：Django admin 資料管理後台、公開地圖

設計原則：
1. 全程容忍空資料庫／當日無資料：count 為 0、列表為空，絕不丟例外。
2. 日期／時間欄位在 DB 是 TEXT（'YYYY-MM-DD HH:MM:SS'），
   因此用字串前綴比對（started_at__startswith）與字串 max 即可正確運作。
3. 只讀不寫：本 view 對資料庫僅做查詢。
"""

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Max
from django.shortcuts import render

from .models import CrawlRun, Showtime

# 台北時區：預設檢視日期以台灣當地「今天」為準，
# 避免伺服器若跑在 UTC 時，深夜時段顯示成前一天。
TAIPEI_TZ = ZoneInfo("Asia/Taipei")

# 錯誤訊息摘要的最大長度（字元數），超過即截斷加省略號
ERROR_SUMMARY_MAX_LEN = 80


def _parse_selected_date(raw_value):
    """
    解析 GET 參數 date（YYYY-MM-DD）。

    格式不合法或未提供時，回傳台北時區的今天，
    確保儀表板永遠有一個合理的預設日期、不會因壞參數而炸掉。
    """
    if raw_value:
        try:
            return datetime.strptime(raw_value.strip(), "%Y-%m-%d").date()
        except ValueError:
            pass  # 格式錯誤 → 退回今天
    return datetime.now(TAIPEI_TZ).date()


def _summarize_error(message):
    """把錯誤訊息壓成單行摘要，超過 ERROR_SUMMARY_MAX_LEN 字元就截斷。"""
    if not message:
        return ""
    one_line = " ".join(str(message).split())  # 換行、多餘空白壓成單一空格
    if len(one_line) > ERROR_SUMMARY_MAX_LEN:
        return one_line[:ERROR_SUMMARY_MAX_LEN] + "…"
    return one_line


@staff_member_required
def dashboard(request):
    """
    營運儀表板首頁。

    GET 參數：
        date（選填）：YYYY-MM-DD，欲檢視的日期；預設為台北時區的今天。
    """
    selected = _parse_selected_date(request.GET.get("date"))
    selected_date = selected.isoformat()  # 'YYYY-MM-DD'，同時餵給查詢與模板

    # ------------------------------------------------------------------
    # 1. 當日各爬蟲來源狀況
    #    started_at 是 TEXT（'YYYY-MM-DD HH:MM:SS'），用前綴比對取當日批次。
    #    每個 source_name 只取「最新一筆」（started_at 最大者）作為該來源的
    #    當日代表狀態；依 started_at 由新到舊排序，最先看到的即為最新。
    # ------------------------------------------------------------------
    day_runs = CrawlRun.objects.filter(started_at__startswith=selected_date)

    source_rows = []
    seen_sources = set()
    for run in day_runs.order_by("-started_at", "-id"):
        source_name = run.source_name or "（未命名來源）"
        if source_name in seen_sources:
            continue  # 同來源較舊的批次略過，只保留最新一筆
        seen_sources.add(source_name)
        source_rows.append(
            {
                "source_name": source_name,
                "run_type": run.run_type,
                "status": run.status,  # 'running' / 'success' / 'failed' / 'partial'
                "started_at": run.started_at or "",
                "finished_at": run.finished_at or "",
                "rows_found": run.rows_found if run.rows_found is not None else 0,
                "rows_saved": run.rows_saved if run.rows_saved is not None else 0,
                "error_summary": _summarize_error(run.error_message),
            }
        )
    # 依來源名稱排序，讓表格順序穩定、方便每天對照
    source_rows.sort(key=lambda row: row["source_name"])

    # ------------------------------------------------------------------
    # 2. 當日 CrawlRun 統計：總數／成功／失敗（failed 與 partial 皆視為失敗）
    # ------------------------------------------------------------------
    total_runs = day_runs.count()
    success_count = day_runs.filter(status="success").count()
    failed_count = day_runs.filter(status__in=("failed", "partial")).count()

    # ------------------------------------------------------------------
    # 3. 當日場次 KPI：總場次、不重複影城據點數、不重複電影數
    # ------------------------------------------------------------------
    day_showtimes = Showtime.objects.filter(show_date=selected_date)
    total_showtimes = day_showtimes.count()
    cinemas_with_showtimes = (
        day_showtimes.values("location_id").distinct().count()
    )
    movies_with_showtimes = day_showtimes.values("movie_id").distinct().count()

    # ------------------------------------------------------------------
    # 4. 上次更新時間：所有 CrawlRun 的 started_at 取最大值。
    #    started_at 是 ISO 風格文字（'YYYY-MM-DD HH:MM:SS'），
    #    字典序即時間序，直接取字串 max 就是最新時間；空表時為 None。
    # ------------------------------------------------------------------
    last_updated = CrawlRun.objects.aggregate(latest=Max("started_at"))["latest"]

    # ------------------------------------------------------------------
    # 5. 前端 GeoJSON 檔案更新時間（不存在時顯示「尚未產生」）
    # ------------------------------------------------------------------
    from django.conf import settings  # 延後匯入，維持模組頂部乾淨

    geojson_path = settings.PROJECT_ROOT / "web" / "data" / "locations.geojson"
    geojson_exists = geojson_path.exists()
    geojson_mtime = (
        datetime.fromtimestamp(geojson_path.stat().st_mtime) if geojson_exists else None
    )

    # ------------------------------------------------------------------
    # 6. 公開地圖網址：可用環境變數覆蓋（例如自訂網域）
    # ------------------------------------------------------------------
    public_map_url = os.environ.get(
        "PUBLIC_MAP_URL", "https://dandadany.github.io/muse-site/"
    )

    context = {
        "selected_date": selected_date,
        "is_today": selected == datetime.now(TAIPEI_TZ).date(),
        "source_rows": source_rows,
        "total_runs": total_runs,
        "success_count": success_count,
        "failed_count": failed_count,
        "total_showtimes": total_showtimes,
        "cinemas_with_showtimes": cinemas_with_showtimes,
        "movies_with_showtimes": movies_with_showtimes,
        "last_updated": last_updated,
        "geojson_exists": geojson_exists,
        "geojson_mtime": geojson_mtime,
        "public_map_url": public_map_url,
    }
    return render(request, "mapdata/dashboard.html", context)
