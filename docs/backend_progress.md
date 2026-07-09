# 後台化開發進度與接手文件

> 這份文件是「續接錨點」。任何人（或下一個 session）接手時，先讀這份，就能知道**做到哪、為什麼這樣決定、下一步做什麼**。每完成一個階段請更新本檔。

最後更新：2026-07-09
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
| **Phase 0** | 產出 `backend_current_flow.md`（現況盤點）＋ `backend_architecture.md`（架構設計）＋ 本進度文件 | 🟡 進行中 |
| Phase 1 | Django 骨架：可啟動、可登入 `/admin/`、管理員/編輯者兩角色、unmanaged models 對應 8 張表可查看（不動 schema） | ⬜ 未開始 |
| Phase 2 | Admin 顯示優化：各表篩選/搜尋、儀表板（今日各來源成功/失敗、總場次、上次更新） | ⬜ 未開始 |
| Phase 3 | 追蹤電影清單升級為 DB 表（取代 `電影清單.txt` 當真相來源，txt 降級為匯出） | ⬜ 未開始 |
| Phase 4 | 一鍵更新按鈕 → 觸發 GitHub Actions `workflow_dispatch` + 即時 log/狀態 | ⬜ 未開始 |
| Phase 5 | 更新結果頁：各來源 found/saved、回寫 crawl_runs、GeoJSON/KML 是否更新 | ⬜ 未開始 |
| Phase 6 | 人工/爬蟲資料分層落實「人工永遠贏」；地圖預覽連結 | ⬜ 未開始 |
| Phase 7+ | 稽核強化、API 化（/api/map/showtimes 等）、對外整合三出口 | ⬜ 未開始 |

---

## 4. 目前這次 session 做了什麼

- 讀完專案原始碼、schema、BAT、腳本流程與使用者朋友的 v2 企劃。
- 與使用者確認 4 個關鍵架構決策（見上表）。
- 啟動 Phase 0 三份文件的撰寫（多模型分派：Fable 寫架構書、Opus 寫盤點文件、主線寫本進度文件）。

## 5. 下一步（接手者從這裡繼續）

1. 確認 Phase 0 三份文件內容正確、與現況一致。
2. 開始 **Phase 1**：建立 `backend/` Django 專案骨架
   - `backend/manage.py`、`backend/movie_map_admin/{settings,urls}.py`、`backend/mapdata/{models,admin}.py`
   - settings 一開始就設計成可 hosted（環境變數讀 DB 連線、`ALLOWED_HOSTS`、`SECRET_KEY` 走 env）
   - 先用 unmanaged models（`managed = False`）對應現有 8 張表，Admin 能查看，**不動 schema、不搬資料庫**
   - 建立管理員/編輯者兩個群組與權限
3. 每完成一階段回來更新第 3 節狀態表與第 4 節紀錄。
