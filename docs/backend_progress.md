# 後台化開發進度與接手文件

> 這份文件是「續接錨點」。任何人（或下一個 session）接手時，先讀這份，就能知道**做到哪、為什麼這樣決定、下一步做什麼**。每完成一個階段請更新本檔。

最後更新：2026-07-09（Phase 3 完成，已 push）
開發分支：`claude/theater-backend-system-y7wdl0`

---

## 0. 一句話目標

把現有「電影上映影城地圖」專案，變成一個**可登入、多人協作的後台系統**：使用者能新增／修改影城資訊（品牌、地址、經緯度、logo 等人工資料）與追蹤電影清單，並能觸發爬蟲更新場次，最後推上公開地圖。

---

## 1. 已鎖定的架構決策（定案，勿再反覆）

這些是與使用者確認過的決策，後續實作以此為準：

| 項目 | 決策 | 理由 |
|------|------|------|
| 部署模式 | **雲端多人**，各自帳號登入 | 核心需求就是「讓使用者登入」；localhost 做不到多人 |
| 後端框架 | **Django + Django Admin** | 登入/權限/CRUD/篩選幾乎免費；維持 Python 單一語言 |
| 資料庫（控制面） | **Postgres**（雲端免費層，如 Neon/Railway/Fly.io） | 多人同時寫，SQLite 單寫者會鎖 |
| 爬蟲執行 | **GitHub Actions + self-hosted runner（使用者的 Windows）** | 台灣 IP、現成 Playwright、避免 geo-block；觸發/狀態走後台 |
| 爬蟲觸發 | 後台按鈕 → GitHub API `workflow_dispatch` | 不再 `subprocess` 跑 Windows-only BAT |
| 維運 | 自管 Django + 小額雲端（$5~7/月或免費層） | 彈性最大、Python 一致 |
| 權限角色 | **管理員 / 編輯者** 兩種 + created_by/updated_by 稽核 | 公司化需可追蹤誰改了什麼 |

### 核心架構思想：控制面 vs 爬蟲面分離

```
┌──────────────────────────────┐   workflow_dispatch   ┌──────────────────────────────┐
│  控制面 (雲端 Django)          │ ────────────────────► │  爬蟲面 (GitHub Actions)       │
│  常駐、輕量、無瀏覽器           │   (GitHub API)        │  self-hosted runner = 你的 PC  │
│  · 登入/權限/稽核              │                       │  · Playwright 爬 19 家影城     │
│  · 編輯影城/電影 (人工資料)     │ ◄──────────────────── │  · export_geojson → git push   │
│  · 按鈕觸發爬蟲/看狀態/地圖預覽  │   回寫 crawl_runs      │                              │
└──────────────────────────────┘                       └───────────────┬──────────────┘
         Postgres (人工權威資料)                                        ▼
                                                        GitHub Pages (公開靜態地圖，不動)
```

### 三層資料模型（「人工永遠贏」）

1. **Curated（人工權威）**：品牌、據點、地址、經緯度、logo、追蹤電影、使用者、稽核 → 控制面 Postgres 為單一真相來源。
2. **Crawled（機器產出）**：showtimes、crawl_runs、raw_pages → 每天重爬、可拋棄。
3. **Derived（衍生輸出）**：locations.geojson、KML。

同步規則：爬蟲面每次先從控制面拉最新人工資料 → 爬 showtimes → 匯出 → push；**爬蟲只寫第 2 層，絕不覆蓋第 1 層人工欄位**。

---

## 2. 專案現況速查（接手前先懂這些事實）

- 現有資料流：`電影清單.txt` → `scripts/update_map.py` → `scripts/fetch_movie_showtimes.py`（Playwright 爬 19 家）→ SQLite → `scripts/export_geojson.py` → `web/data/locations.geojson` → `更新地圖.bat` git push → GitHub Pages。
- 資料庫 schema 在 `sql/schema.sql`，共 8 張表：`cinema_chains` / `cinema_locations` / `movies` / `movie_targets` / `showtimes` / `crawl_runs` / `raw_pages` / `kml_exports`。
- **SQLite（`data/movie_map.sqlite`）未進 git**（.gitignore 排除），目前無版本、無多人共享。
- **痛點**：`cinema_locations` 混了人工欄位（address/latitude/longitude/display_name）與爬蟲欄位（source_location_code/source_url）；`sql/manual_location_overrides.sql` 就是在補「重爬蓋掉人工修正」的洞。
- **BAT 是 Windows-only** 且自己會 `git push`。
- 前端靜態地圖（`web/`）已完成度高，deploy 在 GitHub Pages，讀 `web/data/locations.geojson`。

詳細盤點見 `docs/backend_current_flow.md`（Phase 0 產出）。
完整架構設計見 `docs/backend_architecture.md`（Phase 0 產出）。

---

## 3. 分階段路線圖

| 階段 | 內容 | 狀態 |
|------|------|------|
| **Phase 0** | 產出 `backend_current_flow.md`（現況盤點）＋ `backend_architecture.md`（架構設計）＋ 本進度文件 | ✅ 完成（已 push） |
| **Phase 1** | Django 骨架：可啟動、可登入 `/admin/`、管理員/編輯者兩角色、unmanaged models 對應 8 張表可查看（不動 schema） | ✅ 完成（已 push，commit 見下） |
| **Phase 2** | Admin 顯示優化：各表篩選/搜尋、儀表板（今日各來源成功/失敗、總場次、上次更新） | ✅ 完成（已 push） |
| **Phase 3** | 追蹤電影清單升級為 DB 表（取代 `電影清單.txt` 當真相來源，txt 降級為匯出） | ✅ 完成（已 push） |
| Phase 4 | 一鍵更新按鈕 → 觸發 GitHub Actions `workflow_dispatch` + 即時 log/狀態 | ⬜ 未開始 |
| Phase 5 | 更新結果頁：各來源 found/saved、回寫 crawl_runs、GeoJSON/KML 是否更新 | ⬜ 未開始 |
| Phase 6 | 人工/爬蟲資料分層落實「人工永遠贏」；地圖預覽連結 | ⬜ 未開始 |
| Phase 7+ | 稽核強化、API 化（/api/map/showtimes 等）、對外整合三出口 | ⬜ 未開始 |

---

## 4. 目前這次 session 做了什麼

- 讀完專案原始碼、schema、BAT、腳本流程與使用者朋友的 v2 企劃。
- 與使用者確認 4 個關鍵架構決策（見上表）。
- 完成 Phase 0 三份文件（Fable 架構書、Opus 盤點文件、主線進度文件），已 push。
- 討論三個爬蟲盤點發現的處置（見下方「待處理的既有程式碼調整」）。
- 啟動 Phase 1 Django 骨架（多模型分派）。

### Phase 1 實作分派與檔案歸屬（若中途中斷，依此接手）

`backend/` 目錄結構：

```
backend/
  manage.py                         (Sonnet)
  requirements.txt                  (Sonnet) Django/dj-database-url/psycopg2/dotenv/whitenoise/gunicorn
  .env.example                      (Sonnet)
  README.md                         (Sonnet) 本機啟動 + 雲端部署說明
  movie_map_admin/
    __init__.py  urls.py  wsgi.py  asgi.py   (Sonnet)
    settings.py                     (Fable) env 驅動 DB：本機連現有 SQLite、雲端 DATABASE_URL 切 Postgres
  mapdata/
    __init__.py  apps.py            (Sonnet)
    migrations/__init__.py          (Sonnet) 只留空 __init__，models 為 unmanaged 不建 migration
    models.py                       (Fable) 8 個 unmanaged models（managed=False）精準對映 schema
    admin.py                        (Opus) 8 個 ModelAdmin + site_header
    management/commands/seed_roles.py  (Opus) 建立「管理員」「編輯者」群組與權限（idempotent）
```

關鍵設計：
- models 全部 `managed = False`，`migrate` 只會在同一個 SQLite 新增 Django 自身表（auth_*, django_*），**不動現有 8 張業務表**。
- 角色：管理員（全權 + 管使用者）／編輯者（人工資料 view/add/change 無 delete、爬蟲產出僅 view）。
- **主線待辦（agents 回來後我做）**：`pip install` 後端依賴 → `python scripts/init_db.py` 產空 schema SQLite → `manage.py check` / `migrate` / `seed_roles` 驗證 models 對映無誤 → 修正 → commit + push。

### 待處理的既有程式碼調整（三個爬蟲盤點發現，現在不動、排入對應 Phase）

1. **威秀 `headless=False`** → 非程式問題，是 runner 部署要求：self-hosted runner 要跑在「有登入桌面的互動 session」，不能裝成背景 Windows Service。排 Phase 4 runner 設定說明。
2. **失敗被吞掉（仍 exit 0、照 push）** → 不改各家 parser；Phase 4/5 在外層加：(a) crawler 多吐機器可讀執行摘要（additive）、(b) Actions workflow 加 publish guard（失敗過多/場次暴跌就先不 push）。
3. **重跑=全覆蓋（來源當掉會清掉舊場次）** → 需使用者先決策 A/B：A 保留舊場次（可能顯示過期）／B 標記「資料暫缺」。定案後才把 DELETE 從「整片全刪」改「只刪本次成功來源」。排 Phase 6，**待使用者拍板**。

## 5. Phase 1 驗證結果（已完成）

在 sandbox 用一個 `scripts/init_db.py` 產生的空 schema SQLite 實測通過：
- `manage.py check` → 0 問題（models/admin/settings 全部正確載入）。
- `manage.py migrate` → 只新增 Django 自身表（auth_*, django_*），**8 張業務表完好未動**。
- `manage.py seed_roles` → 管理員 36 權限、編輯者 16 權限。
- 塞假資料 + Django test client 登入：8 個 admin 列表頁 + 8 個編輯頁全部 200；admin 首頁 200、`/healthz/` 回 ok、根路徑 302 導向 `/admin/`。
- 編輯者權限實測：可改影城品牌✅、不可刪除✅、場次只能看不能改✅、不能管使用者✅。

本機啟動方式見 `backend/README.md`。

## 6. Phase 2 驗證結果（已完成）

- 儀表板 `/dashboard/`（staff 專用）：指定日期（預設今天 Asia/Taipei）各來源成功/失敗、今日總場次、有場次影城數/電影數、上次更新、GeoJSON 更新時間；日期切換器；壞日期參數自動退回今天。
- `admin.py`：CrawlRun 彩色狀態徽章；Showtime 依 電影/日期/品牌(location__chain)/縣市(location__city) 跨表過濾 + `list_select_related` 防 N+1；`admin.site.site_url="/dashboard/"`。
- 根路徑 `/` 改導向 `/dashboard/`。
- 實測：`check` 0 問題；`/dashboard/`、強化後 admin 頁、縣市跨表過濾全部 200。

## 6.4 上線部署（Render，已備妥設定）

使用者要求「後台要能線上」。已備妥 Render 一鍵部署（見 `docs/deploy_render.md`）：
- `render.yaml`（Blueprint：Web 服務 + Postgres）、`backend/build.sh`（build 階段做 pip/collectstatic/migrate/init_business_schema/seed_roles/ensure_admin，因免費方案無 preDeployCommand）。
- `sql/schema_postgres.sql`：8 張業務表的 Postgres DDL（解決前述「managed=False 表不會被 migrate 建立」的雲端問題）。
- `init_business_schema`（Postgres 建表、SQLite no-op）、`ensure_admin`（env 建初始管理員、冪等）兩個部署指令。
- settings 自動信任 `RENDER_EXTERNAL_HOSTNAME`。
- 已本機驗證整條 build 鏈（check/collectstatic/init_business_schema/ensure_admin 冪等）。
- **狀態**：設定就緒，等使用者在 Render 連接此分支、填 `DJANGO_SUPERUSER_*` 後即上線。上線初期業務表資料為空（本機 SQLite → 雲端 Postgres 的資料同步屬 Phase 6）。

## 6.5 Phase 3 驗證結果與重要提醒（已完成）

- 新增第一張 managed 表 `tracked_movie`（`TrackedMovie` model）+ migration `0001_initial`。
- 實測：`makemigrations`/`migrate` 只建 `tracked_movie`，8 張 unmanaged 業務表未被建/改、資料無損；`import_movie_list` 冪等（第二次 0 新建 2 更新）；`export_movie_list` 往返格式與現有解析器相容且覆寫前備份到 `data/backup/`；admin 稽核 `created_by/updated_by` 自動填入；`seed_roles` 管理員 40／編輯者 19；`check` 0 問題；儀表板與既有 admin 全部仍 200。
- 過程插曲：三個 Phase 3 subagent 因 session 額度用盡中途失敗（Fable 已寫入 model、Opus 已寫入 admin，但 seed_roles/兩個 command/README/.gitignore 未完成）；由主線接手補完並驗證。

> ⚠️ **雲端部署重要提醒（Phase 4/6 要處理）**：因 8 張業務表是 `managed=False`，在**全新的雲端 Postgres** 上跑 `migrate` **不會**建立這 8 張表——只會建 `tracked_movie` 與 Django 自身表。因此控制面 Postgres 的那 8 張表需要另外建立（用 `sql/schema.sql`，或由爬蟲面同步）。本機 SQLite 因表已存在故無此問題。此點已列入架構書風險 R，Phase 6「雙 DB 同步」會正式解決。

## 7. 下一步（接手者從這裡繼續）— Phase 4

目標：後台一顆「一鍵更新」按鈕 → 觸發 GitHub Actions（self-hosted runner）跑爬蟲 → 回寫狀態。
1. **GitHub Actions workflow**（`.github/workflows/crawl.yml`，`workflow_dispatch` 可帶參數 date）：在 self-hosted runner 上跑 `export_movie_list`（讓 txt = 最新追蹤片單）→ `scripts/update_map.py` → commit/push `web/data/locations.geojson`。runner 需求：互動桌面 session（威秀 headless=False）。
2. **後台觸發頁**（`/admin-tools/run-update/` 或 dashboard 按鈕）：透過 GitHub API `POST .../actions/workflows/crawl.yml/dispatches` 觸發；需要一組 GitHub token（存 env，勿進 repo）。建一筆 `crawl_runs`（或新表）記 run_token 供回寫對應。
3. **狀態呈現**：先用 GitHub Actions API 查最近一次 run 狀態顯示於後台；log 連結。
4. **publish guard（對應待辦 #2）**：workflow 內爬完先看成功來源數/場次數，異常則不 push、標記待確認。
5. 防重複點擊（concurrency 鎖）。

之後：Phase 5（更新結果頁：各來源 found/saved、GeoJSON/KML 是否更新）、Phase 6（人工/爬蟲資料分層「人工永遠贏」+ 雙 DB 同步 + 第 4 節末三個待處理發現的 #3 決策）。

> 每完成一階段，回來更新第 3 節狀態表、第 4 節紀錄與本節。
