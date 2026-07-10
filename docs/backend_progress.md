# 後台化開發進度與接手文件

> 這份文件是「續接錨點」。任何人（或下一個 session）接手時，先讀這份，就能知道**做到哪、為什麼這樣決定、下一步做什麼**。每完成一個階段請更新本檔。

最後更新：2026-07-10（Phase 4 本機排程版完成，已 push）
開發分支：`claude/theater-backend-system-y7wdl0`

> 🧭 **路線調整（2026-07-10）**：使用者決定走「**免費本機路線**」，不追求一步到位的雲端多人。
> 形式＝**後台管電影資料（可本機跑）→ 本機每日排程自動爬蟲 → 推送 GitHub Pages**。
> 原 Phase 4（GitHub Actions + self-hosted runner + token）改為更簡單的**本機排程版**（見下）。
> 雲端 Render 部署設定仍保留在 repo（`render.yaml` 等），日後若要線上多人可直接用；
> 若要「完全免費且線上多人」，另一條路是 HTML + Supabase（需重寫前端，暫不做）。

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
| **Phase 4（本機排程版）** | `scripts/daily_update.py`：後台匯出電影→爬蟲→GeoJSON→git push；`更新地圖.bat` 改走它；排程文件 | ✅ 完成（已 push） |
| ~~Phase 4（Actions 版）~~ | GitHub Actions + self-hosted runner + token 觸發 | ⏸ 暫緩（改走本機排程） |
| **Phase 5** | 後台看更新結果：儀表板各來源成功/失敗 + 資料品質提醒（失敗來源的影城今天不顯示） | ✅ 完成（已 push） |
| **Phase 6** | 「沒抓到=不顯示 pin」確認為現有邏輯；爬蟲改 per-source 清除，避免重跑誤傷好資料 | ✅ 完成（已 push） |
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
3. **重跑=全覆蓋（來源當掉會清掉舊場次）** → ✅ **已於 Phase 6 解決**。使用者拍板：「沒抓到就不顯示 pin」（本來就是地圖邏輯：`export_geojson` 只顯示有 showtimes 的影城）。爬蟲已從「開頭全刪」改為「各來源成功時才清自己上次資料」（`clear_source_showtimes`），失敗來源保留好資料、不誤傷別家；舊行為留在 `--wipe-all`。

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
- **狀態**：設定就緒，等使用者在 Render 連接此分支、填 `DJANGO_SUPERUSER_*` 後即上線。
- **SQLite→雲端資料匯入（已做，Phase 6 初次匯入提前）**：`import_from_sqlite` 指令把本機人工資料（品牌/據點/電影/追蹤目標，可選場次）以自然鍵 upsert 匯入目前 DB；本機把 `DATABASE_URL` 指向 Render 外部連線字串即可灌上雲端。已驗證跨 DB 匯入筆數一致、地址/經緯度保留、冪等。用法見 `docs/deploy_render.md`。

## 6.5 Phase 3 驗證結果與重要提醒（已完成）

- 新增第一張 managed 表 `tracked_movie`（`TrackedMovie` model）+ migration `0001_initial`。
- 實測：`makemigrations`/`migrate` 只建 `tracked_movie`，8 張 unmanaged 業務表未被建/改、資料無損；`import_movie_list` 冪等（第二次 0 新建 2 更新）；`export_movie_list` 往返格式與現有解析器相容且覆寫前備份到 `data/backup/`；admin 稽核 `created_by/updated_by` 自動填入；`seed_roles` 管理員 40／編輯者 19；`check` 0 問題；儀表板與既有 admin 全部仍 200。
- 過程插曲：三個 Phase 3 subagent 因 session 額度用盡中途失敗（Fable 已寫入 model、Opus 已寫入 admin，但 seed_roles/兩個 command/README/.gitignore 未完成）；由主線接手補完並驗證。

> ⚠️ **雲端部署重要提醒（Phase 4/6 要處理）**：因 8 張業務表是 `managed=False`，在**全新的雲端 Postgres** 上跑 `migrate` **不會**建立這 8 張表——只會建 `tracked_movie` 與 Django 自身表。因此控制面 Postgres 的那 8 張表需要另外建立（用 `sql/schema.sql`，或由爬蟲面同步）。本機 SQLite 因表已存在故無此問題。此點已列入架構書風險 R，Phase 6「雙 DB 同步」會正式解決。

## 7. Phase 4（本機排程版）成果與下一步

### 已完成（本機排程路線）
- `scripts/daily_update.py`：單一進入點。`export_movie_list`（後台→txt，best-effort，後台不可用則退回現有 txt）→ `update_map.py`（爬蟲+GeoJSON）→ git commit/push。旗標：`--date/--skip-export/--no-crawl/--no-push/--no-git/--dry-run`。
- `更新地圖.bat`：改走 `daily_update.py --no-git`，保留原 git 路徑處理與一鍵行為。
- `docs/scheduled_update.md`：Windows 工作排程器 / cron 設定；注意威秀等 headful 來源需「使用者登入時執行」、git push 憑證要先快取。
- 驗證：dry-run 計畫正確；`--no-crawl` 離線路徑正確重出 GeoJSON（實際網路爬蟲需在使用者本機驗證）。

### Phase 5+6 已完成（2026-07-10）
- **Phase 6**：確認「沒抓到=不顯示 pin」本來就是地圖邏輯；爬蟲 `fetch_movie_showtimes.py` 改為 per-source 清除（`clear_source_showtimes`，靠 `showtimes.crawl_run_id→crawl_runs.source_name`），重跑不再誤傷已成功來源。已用臨時 DB 驗證只清該來源、別家保留。
- **Phase 5**：儀表板加「資料品質提醒」橫幅（`failed_count>0` 時），明講失敗來源的影城今天不顯示、可安全重跑。已驗證 200 + 提醒/失敗來源正確顯示。

### 之後可選
- **人工/爬蟲資料分層「人工永遠贏」**：目前使用者的每日流程只寫 showtimes、不動 cinema_locations 的人工欄位（address/lat/lng），所以此風險在現行流程已自然避開；僅在重跑「據點爬蟲/geocode」時才需處理，屆時再做。
- **上線（可選）**：雲端多人用 Render（`docs/deploy_render.md`）；或 HTML+Supabase（需重寫前端）。

## 8. 雲端 Django ↔ 本機爬蟲：資料流與同步原則（定案 2026-07-10）

> 前提：只有在「雲端 Django（Render Postgres）＋ 本機爬蟲（SQLite）」同時存在時才有兩個 DB。
> 純本機路線（Django 也跑本機、同一顆 SQLite）只有一個 DB，不需要同步。

**核心原則：有方向的資料流，不是雙向鏡像；每種資料只有一個主來源；每次執行同步一次（不做即時）。**

### 主來源（唯一真相）
| 資料 | 主來源 |
|---|---|
| 追蹤片單、人工修改、啟用狀態、影城品牌/據點/經緯度 | **雲端 Django（Postgres）** |
| 爬到的場次 showtimes、原始結果 raw_pages | **本機 SQLite** |
| 執行成功/失敗紀錄 crawl_runs | 本機先寫，**回傳雲端**供查看 |
| 公開地圖 GeoJSON | 本機產出 → GitHub Pages |

### 每次執行的流程（sync-per-run）
```
[執行前] 向雲端 Django 拉最新「啟用中的追蹤片單」→ 寫 電影清單.txt
         （拉不到 → 用上次快取的 電影清單.txt，不中斷）
[執行]   本機爬蟲 → 寫本機 SQLite → 產 GeoJSON → 推 Pages
[執行後] 把本次 crawl_runs 摘要（來源/狀態/found/saved/時間/錯誤）回傳雲端
         （回傳失敗 → 留待下次再送，不中斷）
```

### 衝突規則
- 本機**只讀片單、只寫場次**，不改片名/片單 → 與雲端不會改到同一欄，設計上無衝突。
- 片名以雲端 Django 為準；場次以本機為準。

### 容錯（雲端斷線仍可運作）
- 拉片單失敗 → 用上次快取 txt 繼續。
- 本機 SQLite 永遠在本機，不依賴雲端。
- 回傳失敗 → 本機保留、下次重送。

### 明確「暫時不做」
- Postgres↔SQLite 全表雙向同步、秒級監控、兩邊都能改同欄、自動判新舊、直接互傳 DB 檔。

### 落地里程碑（下一步實作）
1. Django 是片單/設定唯一來源 ✅（TrackedMovie 已是）
2. 本機執行前自動向**雲端**取片單（+ 拉不到用快取）— **待做**（目前 daily_update 讀「本機」Django，要改讀雲端）
3. 本機執行後回傳 crawl_runs 摘要到雲端 — **待做**
4. 雲端斷線時本機用上次資料續跑 — 部分已有（daily_update 會退回現有 txt），改雲端來源後要保留此 fallback

實作取向（最小）：一支「雲端橋接」小程式，用 `CLOUD_DATABASE_URL`（Render 外部連線字串）直接讀 `tracked_movie`、寫 `crawl_runs` 摘要；不動本機 SQLite 的 showtimes。之後要更嚴謹再升級成 Django API + token。

> 提醒：subagent 會受 session 額度限制（本階段起改由主線直接實作較穩）。

> 每完成一階段，回來更新第 3 節狀態表、第 4 節紀錄與本節。
