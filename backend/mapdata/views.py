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

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Max
from django.shortcuts import render

from .models import CrawlReport, CrawlRun, Showtime

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


def _stats_from_report(report):
    """從本機回傳的 CrawlReport（摘要）組出儀表板數字。

    雲端 Django 沒有 showtimes/crawl_runs 明細（那些在本機），只有本機透過 API
    回傳的摘要。這裡把摘要攤平成與本機路徑相同的 context 欄位，讓模板不必分兩套。
    """
    try:
        payload = json.loads(report.payload or "{}")
    except (ValueError, TypeError):
        payload = {}
    summary = payload.get("summary", {}) or {}
    sources = payload.get("sources", []) or []

    source_rows = [
        {
            "source_name": s.get("name") or "（未命名來源）",
            "run_type": "showtimes",
            "status": s.get("status", "unknown"),
            "started_at": "",  # 明細在本機，雲端摘要不含逐筆時間
            "finished_at": "",
            "rows_found": s.get("found", 0) or 0,
            "rows_saved": s.get("saved", 0) or 0,
            "error_summary": _summarize_error(s.get("error_message")),
        }
        for s in sources
    ]
    source_rows.sort(key=lambda row: row["source_name"])

    return {
        "source_rows": source_rows,
        "total_runs": summary.get("sources_total", report.sources_total or 0),
        "success_count": summary.get("sources_success", report.sources_success or 0),
        "failed_count": summary.get("sources_failed", report.sources_failed or 0),
        "total_showtimes": summary.get("showtimes_saved", report.showtimes_saved or 0),
        "cinemas_with_showtimes": summary.get("cinemas_with_showtimes", 0),
        "movies_with_showtimes": summary.get("movies_with_showtimes", 0),
        "last_updated": report.finished_at or report.started_at,
        "data_from": "report",
        "report_run_id": report.run_id,
        "report_worker": report.worker_name,
    }


def _stats_from_local(selected_date):
    """從本機的 CrawlRun / Showtime 明細直接計算（本機執行後台時用）。"""
    day_runs = CrawlRun.objects.filter(started_at__startswith=selected_date)

    source_rows = []
    seen_sources = set()
    for run in day_runs.order_by("-started_at", "-id"):
        source_name = run.source_name or "（未命名來源）"
        if source_name in seen_sources:
            continue
        seen_sources.add(source_name)
        source_rows.append(
            {
                "source_name": source_name,
                "run_type": run.run_type,
                "status": run.status,
                "started_at": run.started_at or "",
                "finished_at": run.finished_at or "",
                "rows_found": run.rows_found if run.rows_found is not None else 0,
                "rows_saved": run.rows_saved if run.rows_saved is not None else 0,
                "error_summary": _summarize_error(run.error_message),
            }
        )
    source_rows.sort(key=lambda row: row["source_name"])

    day_showtimes = Showtime.objects.filter(show_date=selected_date)
    return {
        "source_rows": source_rows,
        "total_runs": day_runs.count(),
        "success_count": day_runs.filter(status="success").count(),
        "failed_count": day_runs.filter(status__in=("failed", "partial")).count(),
        "total_showtimes": day_showtimes.count(),
        "cinemas_with_showtimes": day_showtimes.values("location_id").distinct().count(),
        "movies_with_showtimes": day_showtimes.values("movie_id").distinct().count(),
        "last_updated": CrawlRun.objects.aggregate(latest=Max("started_at"))["latest"],
        "data_from": "local",
        "report_run_id": None,
        "report_worker": None,
    }


@staff_member_required
def dashboard(request):
    """
    營運儀表板首頁。

    GET 參數：
        date（選填）：YYYY-MM-DD，欲檢視的日期；預設為台北時區的今天。

    資料來源：優先讀當日「本機回傳的最新執行報告（CrawlReport）」；若當日沒有
    報告（例如純本機模式、或雲端尚未收到），則退回本機 CrawlRun/Showtime 明細計算。
    """
    selected = _parse_selected_date(request.GET.get("date"))
    selected_date = selected.isoformat()  # 'YYYY-MM-DD'，同時餵給查詢與模板

    reports = CrawlReport.objects.filter(show_date=selected_date).order_by("-created_at")
    # skipped 只代表匯出/排程被略過，沒有新的場次摘要；不能讓它覆蓋同日
    # 已完成的 partial_success/success 報告，否則儀表板會顯示成 0 場。
    report = reports.exclude(status="skipped").first() or reports.first()
    stats = _stats_from_report(report) if report else _stats_from_local(selected_date)

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

    # 網站流量（GA4）：防禦式，未設定/失敗都回傳可安全渲染的結果。
    from . import ga4

    context = {
        "selected_date": selected_date,
        "is_today": selected == datetime.now(TAIPEI_TZ).date(),
        "geojson_exists": geojson_exists,
        "geojson_mtime": geojson_mtime,
        "public_map_url": public_map_url,
        "ga4": ga4.fetch_metrics(),
        **stats,  # source_rows / 各項 KPI / last_updated / data_from / report_run_id / report_worker
    }
    return render(request, "mapdata/dashboard.html", context)
