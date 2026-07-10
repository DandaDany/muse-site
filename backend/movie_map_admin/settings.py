"""
Django settings for movie_map_admin project.

台灣電影上映影城地圖 — 後台管理系統設定檔。

關鍵設計：
- 本設定完全由環境變數驅動（env-driven），以利日後 hosted 到雲端多人使用。
- 資料庫：本機「預設」直接連現有的 SQLite（data/movie_map.sqlite），
  絕不搬動、不修改現有 schema；部署到雲端時，只要設定環境變數
  DATABASE_URL 即可無痛切換到 Postgres（透過 dj-database-url 解析）。
- 靜態檔：雲端環境用 WhiteNoise 直接由 Django 供應 /admin 的靜態檔，
  不需另架 Nginx / CDN。
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# BASE_DIR = backend/（Django 專案根目錄）
BASE_DIR = Path(__file__).resolve().parent.parent

# PROJECT_ROOT = repo 根目錄，用來定位現有的 data/movie_map.sqlite
PROJECT_ROOT = BASE_DIR.parent

# 若 backend/.env 存在，先載入其中的環境變數（本機開發用；雲端由平台注入）
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# 安全性設定
# ---------------------------------------------------------------------------

# 正式環境務必以環境變數 DJANGO_SECRET_KEY 覆蓋；以下預設值僅供本機開發
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-movie-map-admin-do-not-use-in-production",
)

# DJANGO_DEBUG=1 開啟除錯模式（本機預設開啟；雲端請設為 0）
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

# 允許的主機名稱：以逗號分隔，例如 DJANGO_ALLOWED_HOSTS=example.com,admin.example.com
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

# CSRF 信任來源：以逗號分隔的完整 origin，例如
# DJANGO_CSRF_TRUSTED_ORIGINS=https://admin.example.com
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# Render 部署：平台會提供服務的外部網域，這裡自動信任，免手動填 hostname。
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")

# ---------------------------------------------------------------------------
# 應用程式定義
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 專案 app：唯讀對映現有 8 張表的 unmanaged models
    "mapdata",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise 必須緊接在 SecurityMiddleware 之後，供雲端環境服務靜態檔
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "movie_map_admin.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "movie_map_admin.wsgi.application"

# ---------------------------------------------------------------------------
# 資料庫（本專案的關鍵設定）
# ---------------------------------------------------------------------------
# 切換邏輯：
# 1. 雲端／正式環境：設定環境變數 DATABASE_URL（例如 postgres://user:pass@host/db），
#    由 dj-database-url 解析並啟用連線重用（conn_max_age=600）。
# 2. 本機預設：直接連現有的 SQLite 檔案 data/movie_map.sqlite（位於 repo 根目錄），
#    搭配 mapdata 的 unmanaged models（managed=False），絕不修改現有 schema。

if os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.parse(
            os.environ["DATABASE_URL"],
            conn_max_age=600,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(PROJECT_ROOT / "data" / "movie_map.sqlite"),
        }
    }

# ---------------------------------------------------------------------------
# 密碼驗證
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# 國際化（台灣繁體中文介面 / 台北時區）
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "zh-hant"

TIME_ZONE = "Asia/Taipei"

USE_I18N = True

USE_TZ = True

# ---------------------------------------------------------------------------
# 靜態檔（雲端由 WhiteNoise 供應，含壓縮與快取指紋）
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Django 4.2+ 的 STORAGES 寫法：靜態檔改用 WhiteNoise 的壓縮 + manifest 儲存後端
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ---------------------------------------------------------------------------
# 其他
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
