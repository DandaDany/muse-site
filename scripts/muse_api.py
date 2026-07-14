"""本機 Worker ↔ 雲端 Django 的 API 客戶端與快取/佇列工具。

職責：
- 拉片單：GET /api/tracked-movies/，驗證後原子更新 JSON 快取與 電影清單.txt；
  失敗則退回上次快取（雲端斷線仍可執行）。
- 回傳報告：POST /api/crawl-report/，採 outbox 模式（先落地 pending_reports，
  上傳成功才刪檔），以 run_id 冪等避免重複。

環境變數：
    MUSE_API_BASE_URL   例如 https://muse-backend-xxxx.onrender.com（未設 = 純本機模式）
    MUSE_API_TOKEN      與雲端 CRAWLER_API_TOKEN 相同
    MUSE_WORKER_NAME    選填，預設本機 hostname
"""

from __future__ import annotations

import json
import os
import socket
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # 讓沒有安裝後台相依套件的本機環境仍可使用快取/爬蟲
    load_dotenv = None

PROJECT_DIR = Path(__file__).resolve().parents[1]
MOVIE_LIST = PROJECT_DIR / "電影清單.txt"
CACHE_DIR = PROJECT_DIR / "cache"
CACHE_JSON = CACHE_DIR / "tracked_movies.json"
CACHE_META = CACHE_DIR / "tracked_movies_meta.json"
PENDING_DIR = PROJECT_DIR / "data" / "output" / "pending_reports"

# Windows 工作排程器不一定會繼承互動式終端機的環境變數；
# 優先載入專案根目錄的 .env，再由真正的環境變數覆蓋。
def _load_local_env() -> None:
    env_path = PROJECT_DIR / ".env"
    if load_dotenv:
        load_dotenv(env_path)
        return
    # 最小 fallback：即使排程環境尚未安裝 python-dotenv，也能讀取簡單 KEY=VALUE 設定。
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def api_base() -> str:
    return os.environ.get("MUSE_API_BASE_URL", "").rstrip("/")


def api_token() -> str:
    return os.environ.get("MUSE_API_TOKEN", "")


def worker_name() -> str:
    return os.environ.get("MUSE_WORKER_NAME") or socket.gethostname()


def _request(url, method="GET", body=None, timeout=30):
    headers = {}
    if api_token():
        headers["Authorization"] = f"Bearer {api_token()}"
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8") or "{}"
        return resp.status, json.loads(raw)


def _atomic_write(path: Path, text: str, encoding="utf-8") -> None:
    """先寫 .tmp 再 rename，避免寫到一半中斷造成殘檔。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, path)


# --- 片單：拉取、驗證、快取 ------------------------------------------------

def _valid_payload(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    movies = payload.get("movies")
    if not isinstance(movies, list):
        return False
    if payload.get("count") != len(movies):
        return False
    return True


def write_movie_list_txt(movies) -> None:
    """把片單原子寫入 電影清單.txt（與現有爬蟲解析相容：每行「N. 片名」）。"""
    lines = [f"{i}. {m['title']}" for i, m in enumerate(movies, start=1)]
    _atomic_write(MOVIE_LIST, "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8-sig")


def _update_cache(payload) -> None:
    _atomic_write(CACHE_JSON, json.dumps(payload, ensure_ascii=False, indent=2))
    meta = {
        "fetched_at": now_iso(),
        "api_url": f"{api_base()}/api/tracked-movies/",
        "movie_count": payload.get("count"),
        "version": payload.get("version"),
    }
    _atomic_write(CACHE_META, json.dumps(meta, ensure_ascii=False, indent=2))


def _load_cache():
    if CACHE_JSON.exists():
        return json.loads(CACHE_JSON.read_text(encoding="utf-8"))
    return None


def cache_age_seconds():
    if not CACHE_META.exists():
        return None
    try:
        meta = json.loads(CACHE_META.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(meta["fetched_at"])
        return int((datetime.now(fetched.tzinfo) - fetched).total_seconds())
    except Exception:
        return None


def pull_movie_list():
    """取得要爬的片單。回傳 (movies|None, meta)。

    meta.source ∈ {api, cache, none}；並含 version/count/cache_age_seconds/api_error。
    - api：成功且通過驗證，已更新快取。
    - cache：API 失敗或回傳空清單，改用上次快取。
    - none：未設定 API 或無快取，交由呼叫端使用現有 電影清單.txt。
    movies 為 None 表示呼叫端不要覆蓋現有 txt（沿用上次）。
    """
    base = api_base()
    if not base:
        return None, {"source": "none", "note": "未設定 MUSE_API_BASE_URL，使用現有 電影清單.txt"}
    try:
        status, payload = _request(f"{base}/api/tracked-movies/")
        if status != 200:
            raise RuntimeError(f"HTTP {status}")
        if not _valid_payload(payload):
            raise RuntimeError("payload 格式不合法")
        if payload.get("count", 0) == 0:
            # 空清單視為可疑：保留上次快取，不覆蓋 txt。
            return None, {
                "source": "cache", "version": None, "count": 0,
                "cache_age_seconds": cache_age_seconds(),
                "api_error": "API 回傳空清單，保留上次快取",
            }
        _update_cache(payload)
        return payload["movies"], {
            "source": "api", "version": payload.get("version"),
            "count": payload.get("count"), "cache_age_seconds": 0,
        }
    except Exception as exc:
        cached = _load_cache()
        if cached and isinstance(cached.get("movies"), list):
            return cached["movies"], {
                "source": "cache", "version": cached.get("version"),
                "count": cached.get("count"), "cache_age_seconds": cache_age_seconds(),
                "api_error": f"{type(exc).__name__}: {exc}",
            }
        return None, {
            "source": "none", "api_error": f"{type(exc).__name__}: {exc}",
            "note": "API 失敗且無快取，使用現有 電影清單.txt",
        }


# --- 報告：outbox 待送佇列 -------------------------------------------------

def save_pending_report(report) -> Path:
    path = PENDING_DIR / f"{report['run_id']}.json"
    _atomic_write(path, json.dumps(report, ensure_ascii=False, indent=2))
    return path


def _post_report(report, timeout=30):
    base = api_base()
    if not base:
        raise RuntimeError("未設定 MUSE_API_BASE_URL")
    status, resp = _request(f"{base}/api/crawl-report/", method="POST", body=report, timeout=timeout)
    if status not in (200, 201):
        raise RuntimeError(f"HTTP {status}")
    return resp


def flush_pending_reports():
    """上傳所有待送報告，成功才刪檔（先落地再上傳的 outbox）。回傳 (sent, failed)。"""
    if not PENDING_DIR.exists():
        return 0, 0
    pending_paths = sorted(PENDING_DIR.glob("*.json"))
    if not pending_paths:
        return 0, 0
    if not api_base():
        print("[warn] MUSE_API_BASE_URL 未設定；報告保留在 pending_reports，未送出")
        return 0, len(pending_paths)
    if not api_token():
        print("[warn] MUSE_API_TOKEN 未設定；報告保留在 pending_reports，未送出")
        return 0, len(pending_paths)
    sent = failed = 0
    for path in pending_paths:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            _post_report(report)
            path.unlink()
            sent += 1
        except Exception as exc:
            print(f"[warn] 待送報告上傳失敗（{path.name}）：{exc}")
            failed += 1
    return sent, failed
