"""機器對機器 API：本機 daily_update（Worker）與雲端 Django（Control Plane）的橋接。

端點：
- GET  /api/tracked-movies/  本機「拉」要爬什麼（啟用中的追蹤片單 + 版本）。
- POST /api/crawl-report/    本機「回傳」執行摘要（以 run_id 冪等 upsert）。

驗證：Authorization: Bearer <CRAWLER_API_TOKEN>（環境變數，非人類登入）。
未設定 token → 503（避免不小心開放）；token 不符 → 401。
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Max, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import CinemaChain, CinemaLocation, CrawlReport, TrackedMovie

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def _check_token(request) -> JsonResponse | None:
    """驗證 Bearer token。通過回傳 None，否則回傳錯誤 JsonResponse。"""
    expected = getattr(settings, "CRAWLER_API_TOKEN", "") or ""
    if not expected:
        return JsonResponse(
            {"error": "API 未設定 CRAWLER_API_TOKEN，暫不開放。"}, status=503
        )
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    if token != expected:
        return JsonResponse({"error": "未授權。"}, status=401)
    return None


def _aliases_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [line.strip() for line in raw.splitlines() if line.strip()]


@require_http_methods(["GET"])
def tracked_movies(request):
    """回傳啟用中的追蹤片單 + 版本（版本 = 所有片單 updated_at 最大值的 epoch）。"""
    denied = _check_token(request)
    if denied:
        return denied

    # 上映日期閘門：只回「今天（台北）不早於上映日期」的電影；未到日期者跳過。
    # 上映日期留空（target_date is null）= 不設限，一律納入。
    today = datetime.now(TAIPEI_TZ).date()
    qs = (
        TrackedMovie.objects.filter(is_active=True)
        .filter(Q(target_date__isnull=True) | Q(target_date__lte=today))
        .order_by("sort_order", "title")
    )
    # version 仍以「所有啟用片單」的 updated_at 最大值計，讓後台任何調整都會改版本。
    latest = TrackedMovie.objects.filter(is_active=True).aggregate(m=Max("updated_at"))["m"]
    version = int(latest.timestamp()) if latest else 0

    movies = [
        {
            "id": m.id,
            "title": m.title,
            "aliases": _aliases_list(m.aliases),
            "target_date": m.target_date.isoformat() if m.target_date else None,
            "enabled": True,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        }
        for m in qs
    ]
    return JsonResponse(
        {
            "generated_at": timezone.now().isoformat(),
            "version": version,
            "count": len(movies),
            "movies": movies,
        }
    )


def _upsert_location_codes(request) -> JsonResponse:
    """POST /api/cinema-master/：回寫即時爬到的據點代碼到既有據點。

    body: {"locations": [{"chain_name","location_name","source_location_code"}, ...]}
    以 (chain_name, location_name) 找既有據點，只更新有帶代碼者；找不到就記入 skipped。
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "無效的 JSON。"}, status=400)

    locations = data.get("locations")
    if not isinstance(locations, list):
        return JsonResponse({"error": "缺少 locations 陣列。"}, status=400)

    updated = unchanged = skipped = 0
    for item in locations:
        if not isinstance(item, dict):
            skipped += 1
            continue
        code = (item.get("source_location_code") or "").strip()
        chain_name = (item.get("chain_name") or "").strip()
        location_name = (item.get("location_name") or "").strip()
        if not code or not chain_name or not location_name:
            skipped += 1
            continue
        obj = (
            CinemaLocation.objects
            .filter(chain__chain_name=chain_name, location_name=location_name)
            .first()
        )
        if obj is None:
            skipped += 1
            continue
        if (obj.source_location_code or "") == code:
            unchanged += 1
            continue
        obj.source_location_code = code
        obj.save(update_fields=["source_location_code"])
        updated += 1

    return JsonResponse(
        {"ok": True, "updated": updated, "unchanged": unchanged, "skipped": skipped}
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def cinema_master(request):
    """影城主檔 API（啟用中的品牌 + 據點），供爬蟲 Worker 使用。

    GET ：回傳影城地址簿（含爬蟲必需的 source_location_code、經緯度等）。
          GitHub Actions 每次排程爬蟲前呼叫，重建本機 data/movie_map.sqlite。
    POST：回寫「即時爬到的據點代碼」。新光/in89/國賓 的代碼是每次爬蟲即時抓的，
          爬完把它們 POST 回來持久化到 Postgres，後台才會累積成完整單一來源；
          之後即使某天該官網逾時，後台仍有上次存好的代碼可用。
          只以自然鍵 (品牌, 據點名) 更新既有據點的 source_location_code，
          找不到就略過（不新建，避免產生無座標的幽靈據點）。
    """
    denied = _check_token(request)
    if denied:
        return denied

    if request.method == "POST":
        return _upsert_location_codes(request)

    chains = [
        {
            "id": c.id,
            "chain_name": c.chain_name,
            "official_url": c.official_url,
            "crawl_url": c.crawl_url,
            "booking_url": c.booking_url,
            "all_locations_assumed_showing": bool(c.all_locations_assumed_showing),
            "notes": c.notes,
            "active": bool(c.active),
        }
        for c in CinemaChain.objects.filter(active=True).order_by("id")
    ]
    locations = [
        {
            "id": loc.id,
            "chain_id": loc.chain_id,
            "location_name": loc.location_name,
            "display_name": loc.display_name,
            "address": loc.address,
            "city": loc.city,
            "district": loc.district,
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "source_location_code": loc.source_location_code,
            "location_url": loc.location_url,
            "source_url": loc.source_url,
            "notes": loc.notes,
            "active": bool(loc.active),
        }
        for loc in CinemaLocation.objects.filter(active=True).order_by("id")
    ]
    return JsonResponse(
        {
            "generated_at": timezone.now().isoformat(),
            "chain_count": len(chains),
            "location_count": len(locations),
            "chains": chains,
            "locations": locations,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def crawl_report(request):
    """接收本機執行摘要，以 run_id 冪等 upsert 到 crawl_report。"""
    denied = _check_token(request)
    if denied:
        return denied

    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "無效的 JSON。"}, status=400)

    run_id = (data.get("run_id") or "").strip()
    if not run_id:
        return JsonResponse({"error": "缺少 run_id。"}, status=400)

    ml = data.get("movie_list") or {}
    summary = data.get("summary") or {}
    git = data.get("git") or {}

    defaults = {
        "worker_name": data.get("worker_name"),
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
        "show_date": data.get("show_date"),
        "status": data.get("status") or "unknown",
        "movie_list_source": ml.get("source"),
        "movie_list_version": ml.get("version"),
        "movie_list_count": ml.get("count"),
        "cache_age_seconds": ml.get("cache_age_seconds"),
        "sources_total": summary.get("sources_total") or 0,
        "sources_success": summary.get("sources_success") or 0,
        "sources_failed": summary.get("sources_failed") or 0,
        "showtimes_found": summary.get("showtimes_found") or 0,
        "showtimes_saved": summary.get("showtimes_saved") or 0,
        "git_push_status": git.get("push_status"),
        "commit_sha": git.get("commit_sha"),
        "payload": json.dumps(data, ensure_ascii=False),
    }

    obj, created = CrawlReport.objects.update_or_create(
        run_id=run_id, defaults=defaults
    )
    return JsonResponse({"ok": True, "run_id": run_id, "created": created}, status=200 if not created else 201)
