"""GA4 Data API：抓地圖網站的流量摘要，顯示在營運儀表板。

全程防禦式：未設定或任何錯誤都回傳可安全渲染的結果，絕不讓儀表板壞掉。

環境變數（未設定 GA4_PROPERTY_ID → 顯示「尚未連接」狀態）：
- GA4_PROPERTY_ID：GA4 資源 ID（純數字，例如 123456789）
- 憑證二選一：
  - GA4_CREDENTIALS_JSON：服務帳號金鑰 JSON「內容」整段貼進環境變數（雲端推薦）
  - GOOGLE_APPLICATION_CREDENTIALS：金鑰 JSON 檔路徑
- GA4_PROPERTY_URL（選填）：GA4 報表網址，供「開啟 GA4」按鈕。

設定步驟見 docs/ga4_setup.md。
"""

from __future__ import annotations

import json
import os
import time

# 模組層級快取，避免每次開儀表板都打 GA4 API（有配額、也較慢）。
_CACHE: dict = {"at": 0.0, "data": None}
_TTL_SECONDS = 600  # 10 分鐘


def property_url() -> str:
    return os.environ.get("GA4_PROPERTY_URL", "https://analytics.google.com/")


def _load_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.oauth2 import service_account

    scopes = ["https://www.googleapis.com/auth/analytics.readonly"]
    raw = os.environ.get("GA4_CREDENTIALS_JSON")
    if raw:
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        return BetaAnalyticsDataClient(credentials=creds)
    # 否則走 GOOGLE_APPLICATION_CREDENTIALS（Application Default Credentials）
    return BetaAnalyticsDataClient()


def fetch_metrics() -> dict:
    """回傳流量摘要 dict。永遠可安全渲染。

    keys: configured(bool), error(str|None), property_url, range,
          active_users, page_views, sessions, select_movie, select_cinema,
          movie_selections
    """
    prop = os.environ.get("GA4_PROPERTY_ID")
    if not prop:
        return {"configured": False, "property_url": property_url()}

    now = time.time()
    if _CACHE["data"] and now - _CACHE["at"] < _TTL_SECONDS:
        return _CACHE["data"]

    try:
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            RunReportRequest,
        )

        client = _load_client()
        prop_path = f"properties/{prop}"
        date_range = DateRange(start_date="7daysAgo", end_date="today")

        # 概況：活躍使用者、瀏覽次數、工作階段（皆為標準指標）
        overview = client.run_report(
            RunReportRequest(
                property=prop_path,
                date_ranges=[date_range],
                metrics=[
                    Metric(name="activeUsers"),
                    Metric(name="screenPageViews"),
                    Metric(name="sessions"),
                ],
            )
        )
        users = views = sessions = 0
        if overview.rows:
            mv = overview.rows[0].metric_values
            users, views, sessions = (int(mv[0].value), int(mv[1].value), int(mv[2].value))

        # 各事件次數（用標準維度 eventName，不需註冊自訂維度）
        events = client.run_report(
            RunReportRequest(
                property=prop_path,
                date_ranges=[date_range],
                dimensions=[Dimension(name="eventName")],
                metrics=[Metric(name="eventCount")],
                limit=50,
            )
        )
        counts = {
            row.dimension_values[0].value: int(row.metric_values[0].value)
            for row in events.rows
        }

        data = {
            "configured": True,
            "error": None,
            "property_url": property_url(),
            "range": "近 7 日",
            "active_users": users,
            "page_views": views,
            "sessions": sessions,
            "select_movie": counts.get("select_movie", 0),
            "select_cinema": counts.get("select_cinema", 0),
            "movie_selections": [],
            "movie_selection_error": None,
        }

        # movie_title 是事件參數；GA4 必須先建立同名的「自訂維度」後，
        # Data API 才能用 customEvent:movie_title 分組查詢。
        try:
            movie_events = client.run_report(
                RunReportRequest(
                    property=prop_path,
                    date_ranges=[date_range],
                    dimensions=[
                        Dimension(name="eventName"),
                        Dimension(name="customEvent:movie_title"),
                    ],
                    metrics=[Metric(name="eventCount")],
                    limit=100,
                )
            )
            data["movie_selections"] = [
                {
                    "title": row.dimension_values[1].value or "（未提供片名）",
                    "count": int(row.metric_values[0].value),
                }
                for row in movie_events.rows
                if row.dimension_values[0].value == "select_movie"
            ]
            data["movie_selections"].sort(key=lambda item: (-item["count"], item["title"]))
        except Exception as exc:
            data["movie_selection_error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # 套件未安裝、憑證錯誤、API 失敗… 一律安全降級
        data = {
            "configured": True,
            "error": f"{type(exc).__name__}: {exc}",
            "property_url": property_url(),
        }

    _CACHE.update(at=now, data=data)
    return data
