# muse-site 後台系統架構設計書

| 項目 | 內容 |
| --- | --- |
| 文件版本 | v1.0 |
| 撰寫日期 | 2026-07-09 |
| 文件狀態 | 定案（依團隊已拍板決策撰寫） |
| 適用專案 | muse-site（台灣電影上映影城地圖） |
| 相關文件 | `DECISIONS.md`、`sql/schema.sql`、`sql/manual_location_overrides.sql` |

---

## 1. 文件目的與範圍

### 1.1 目的

本文件是 muse-site 後台系統的**骨幹設計書**，目的是：

1. 把已拍板的架構決策白紙黑字固定下來，讓團隊成員（現在與未來）不必重新討論「為什麼這樣做」。
2. 定義**控制面（Control Plane）與爬蟲面（Crawl Plane）分離**的整體架構，以及兩者之間的資料同步規則。
3. 作為後續實作（Django 專案、GitHub Actions workflow、資料遷移）的依據：所有實作若與本文件衝突，應先回來修訂本文件。

### 1.2 範圍

**涵蓋**：

- 後台（Django）系統架構、資料模型、權限與稽核設計。
- 爬蟲觸發機制（後台 → GitHub API → self-hosted runner）。
- 雙資料庫（雲端 Postgres ↔ 本機 SQLite）的同步規則。
- 部署拓撲與對外整合出口。

**不涵蓋**：

- 各影城爬蟲的解析邏輯（維持 `scripts/fetch_*.py` 現有實作，另行維護）。
- 前端公開地圖的 UI 細節（見 `DECISIONS.md` 的 Frontend Map 章節）。
- 詳細的 Django model / view 程式碼（屬實作階段產物）。

---

## 2. 現況摘要

### 2.1 一句話資料流

> 純文字的 `電影清單.txt` 定義追蹤目標 → `scripts/update_map.py` 呼叫 `scripts/fetch_movie_showtimes.py`（Playwright 爬 19 家影城場次）寫入 SQLite（`data/movie_map.sqlite`，未進 git）→ `scripts/export_geojson.py` 匯出 `web/data/locations.geojson` → `更新地圖.bat` 執行 git add/commit/push → GitHub Actions 部署 GitHub Pages 靜態 Leaflet 地圖。

### 2.2 現有資料庫（SQLite，8 張表）

| 表 | 性質 | 說明 |
| --- | --- | --- |
| `cinema_chains` | 人工維護 | 影城品牌（名稱、官網、爬蟲 URL、訂票 URL） |
| `cinema_locations` | **混雜（痛點）** | 影城據點；人工欄位與爬蟲欄位同表 |
| `movies` | 人工維護 | 電影主檔 |
| `movie_targets` | 人工維護 | 電影 × 品牌/據點的追蹤目標 |
| `showtimes` | 爬蟲產出 | 場次資料，每次重爬更新 |
| `crawl_runs` | 爬蟲產出 | 爬蟲執行紀錄 |
| `raw_pages` | 爬蟲產出 | 原始頁面快照（除錯用） |
| `kml_exports` | 衍生輸出 | KML 匯出紀錄 |

### 2.3 關鍵痛點

1. **人工修正會被爬蟲蓋掉**：`cinema_locations` 同一張表混了「人工欄位」（`address`、`latitude`、`longitude`、`display_name`）與「爬蟲欄位」（`source_location_code`、`source_url`）。重爬據點資料時會覆寫人工修正過的地址與經緯度，目前靠 `sql/manual_location_overrides.sql` 事後補救——這是補丁，不是架構解。
2. **單機、單人、無權限**：所有維護動作都在一台 Windows 上手動執行 BAT，同事無法協作，也沒有任何操作紀錄可稽核。
3. **追蹤電影清單是純文字檔**：`電影清單.txt` 與 DB 內的 `movies`/`movie_targets` 是兩套來源，容易不同步。
4. **發佈流程綁死 BAT**：`更新地圖.bat` 把「跑爬蟲」與「git 發佈」黏在一起，無法遠端觸發、無法看到執行狀態。

---

## 3. 定案決策清單

以下 4 點為**已拍板定案**，本文件其餘章節皆以此為前提展開：

| # | 決策項 | 定案內容 | 理由摘要 |
| --- | --- | --- | --- |
| D1 | 部署型態 | **雲端多人**：hosted Django + Postgres，團隊成員各自從自己的電腦以帳號登入後台。 | 多人協作需要共享的單一真相來源與帳號權限，本機方案無法滿足。 |
| D2 | 爬蟲執行 | 把使用者現有的 **Windows 機器註冊為 GitHub Actions self-hosted runner**。後台按鈕透過 GitHub API 觸發 `workflow_dispatch`，實際爬蟲在該 Windows 上執行；log 與狀態回寫後台。 | 台灣 IP（避免影城網站 geo-block）、現成的 Playwright 環境、雲端主機不必養瀏覽器。 |
| D3 | 維運模式 | **自管 Django + 小額雲端**（每月約 $5~7 或免費層，候選：Neon / Railway / Fly.io）。維持 **Python 單一語言**。 | 成本可控；團隊技術棧集中在 Python，降低維護負擔。 |
| D4 | 權限角色 | 兩種角色：**管理員**（管使用者、系統設定、觸發爬蟲）與**編輯者**（改影城品牌/據點/經緯度/logo、改追蹤電影）。每筆修改記錄 `created_by` / `updated_by` 做稽核。 | 最小可用的權限模型；先能追責，再談細粒度。 |

---

## 4. 系統架構總覽

### 4.1 核心思想：控制面與爬蟲面分離

整個系統切成三塊，各自的生命週期與資源需求完全不同：

| 面 | 位置 | 特性 | 職責 |
| --- | --- | --- | --- |
| **控制面 Control Plane** | 雲端（Django + Postgres） | 常駐、輕量、**無瀏覽器/無 Playwright** | 登入/權限/稽核、編輯影城與電影、按鈕觸發爬蟲、看執行狀態、地圖預覽 |
| **爬蟲面 Crawl Plane** | GitHub Actions self-hosted runner（使用者的 Windows 機器） | 拋棄式、按需執行、有 Playwright | 拉最新人工資料 → 爬場次 → 匯出 GeoJSON → git push → 回寫狀態 |
| **公開地圖** | GitHub Pages（靜態 Leaflet） | 純靜態、零維運 | 讀 `locations.geojson` 顯示地圖；**維持現狀不動** |

分離的理由：

- 爬蟲需要瀏覽器、台灣 IP、大量記憶體——這些放在便宜的雲端 Django 主機上既貴又不可行；放在 self-hosted runner 上是零成本。
- 控制面需要 24 小時在線給多人登入——這放在使用者的 Windows 上不可靠；放在雲端免費層/小額方案剛剛好。
- 公開地圖已經以靜態檔運作良好，沒有理由改動。

### 4.2 架構圖（ASCII）

```
                ┌─────────────────────────────────────────────┐
                │           控制面 Control Plane（雲端）        │
   團隊成員      │  ┌───────────────┐      ┌────────────────┐  │
  ┌─────────┐   │  │  Django 後台   │─────▶│   Postgres     │  │
  │ 管理員   │──▶│  │  - 登入/權限   │      │  Curated 資料  │  │
  │ 編輯者   │   │  │  - 影城/電影   │      │  (單一真相來源) │  │
  └─────────┘   │  │  - 稽核紀錄    │      │  + crawl_runs  │  │
   瀏覽器登入    │  │  - 觸發爬蟲    │      │    狀態鏡像     │  │
                │  │  - 狀態儀表板  │      └────────────────┘  │
                │  └──────┬────────┘                           │
                └─────────┼─────────────────▲──────────────────┘
                          │ (1) GitHub API  │ (4) 回寫 crawl_runs
                          │  workflow_      │     狀態 / log 摘要
                          │  dispatch       │     (HTTPS + Token)
                          ▼                 │
                ┌──────────────────┐        │
                │   GitHub          │       │
                │  ┌─────────────┐  │       │
                │  │  Actions     │──┼───────┼───┐
                │  │  workflow    │  │       │   │ (2) 派工
                │  └─────────────┘  │       │   ▼
                │  ┌─────────────┐  │  ┌────┴────────────────────────┐
                │  │  git repo    │◀─┼──│ 爬蟲面 Crawl Plane           │
                │  │  (web/data/  │  │  │ self-hosted runner          │
                │  │   *.geojson) │  │  │ = 使用者的 Windows（台灣 IP）│
                │  └──────┬──────┘  │  │  (3) 執行：                  │
                │         │         │  │   a. 從控制面拉 Curated 資料 │
                │  ┌──────▼──────┐  │  │   b. Playwright 爬 19 家影城 │
                │  │ GitHub Pages │  │  │   c. export_geojson.py      │
                │  │ 靜態 Leaflet │  │  │   d. git commit + push      │
                │  └──────┬──────┘  │  └─────────────────────────────┘
                └─────────┼─────────┘
                          ▼
                    ┌──────────┐
                    │ 一般訪客  │  （公開地圖，唯讀）
                    └──────────┘
```

### 4.3 各面互動一覽

| 從 | 到 | 協定/機制 | 內容 |
| --- | --- | --- | --- |
| 控制面 | GitHub | GitHub REST API（`workflow_dispatch`） | 觸發爬蟲 workflow，帶入參數（如指定電影、指定品牌） |
| GitHub Actions | 爬蟲面 | runner 長輪詢（GitHub 原生機制） | 派工給 self-hosted runner |
| 爬蟲面 | 控制面 | HTTPS API + Service Token | 拉取最新 Curated 資料；回寫 `crawl_runs` 狀態與 log 摘要 |
| 爬蟲面 | GitHub repo | git push | 更新 `web/data/locations.geojson` |
| GitHub Pages | 訪客 | 靜態 HTTPS | 公開地圖 |
| 團隊成員 | 控制面 | 瀏覽器 HTTPS + Session 登入 | 所有後台操作 |

---

## 5. 資料架構

### 5.1 三層資料模型

資料依「誰是權威、能不能重建」分為三層。這是整個資料架構的地基：

```
┌──────────────────────────────────────────────────────────────┐
│ 第 1 層 Curated（人工權威）— 控制面 Postgres 為單一真相來源      │
│   品牌 cinema_chains、據點 cinema_locations（人工欄位）、        │
│   logo 對應、電影 movies、追蹤目標 movie_targets、               │
│   使用者 users、稽核 audit log                                  │
│   ★ 只有人（透過後台）能改；爬蟲絕對不寫這一層                    │
├──────────────────────────────────────────────────────────────┤
│ 第 2 層 Crawled（機器產出）— 可拋棄、每天重爬                     │
│   showtimes、crawl_runs、raw_pages                             │
│   ★ 只有爬蟲寫；全刪重建也不心疼                                 │
├──────────────────────────────────────────────────────────────┤
│ 第 3 層 Derived（衍生輸出）— 由 1+2 層計算而得                    │
│   web/data/locations.geojson、KML（kml_exports）                │
│   ★ 永遠可以由上兩層重新匯出，本身不是資料來源                    │
└──────────────────────────────────────────────────────────────┘
```

| 層 | 資料 | 寫入者 | 權威所在 | 遺失了怎麼辦 |
| --- | --- | --- | --- | --- |
| 1 Curated | 品牌、據點、地址、經緯度、logo、追蹤電影、使用者、稽核 | 人（後台） | **控制面 Postgres** | 不可遺失，要備份 |
| 2 Crawled | showtimes、crawl_runs、raw_pages | 爬蟲 | 爬蟲面 SQLite（執行期）；狀態鏡像回 Postgres | 重爬一次即可 |
| 3 Derived | locations.geojson、KML | 匯出腳本 | git repo | 重新匯出即可 |

### 5.2 「人工永遠贏」原則的落實

現況痛點的根治方式，不是繼續用 override SQL 補救，而是**在 schema 層面把人工欄位與爬蟲欄位分家**：

1. **欄位分家**：`cinema_locations` 在控制面 Postgres 中拆為兩組欄位（或兩張表）：
   - 人工組（Curated）：`display_name`、`address`、`latitude`、`longitude`、`city`、`district`、`notes`、logo 對應——只有後台表單能寫。
   - 來源組（Source metadata）：`source_location_code`、`source_url`、`location_url`——爬蟲面據點爬蟲可更新，但**只能更新這一組**。
2. **寫入路徑隔離**：爬蟲腳本的 DB 寫入層以白名單限制可寫的表與欄位（第 2 層全部 + 第 1 層的來源組欄位）；任何試圖寫入人工欄位的操作直接報錯，而不是默默覆蓋。
3. **`manual_location_overrides.sql` 退役**：資料遷移到 Postgres 時，先套用該 override，之後此檔案封存不再使用——人工修正從此直接在後台改，且不會被蓋掉。
4. **衝突呈現而非衝突覆蓋**：若爬蟲發現來源網站的據點資訊與人工資料不一致（例如影城搬家），不覆寫，而是在 `crawl_runs` 中記為「差異提示」，由編輯者在後台人工確認後修改。

### 5.3 雙 DB 架構與同步規則

系統存在兩個資料庫，角色明確不對等：

| DB | 位置 | 角色 |
| --- | --- | --- |
| Postgres | 雲端（Neon/Railway/Fly.io） | **主**：第 1 層唯一權威 + 第 2 層狀態鏡像（crawl_runs、showtimes 彙總） |
| SQLite（`data/movie_map.sqlite`） | 爬蟲面 Windows | **工作區快取**：爬蟲執行期間的本地工作資料庫，可隨時重建 |

**每次爬蟲更新的同步流程（單向環，不做雙向同步）**：

```
(1) 拉  ：爬蟲面從控制面 API 拉最新 Curated 資料
          （品牌、據點、追蹤電影清單）→ 寫入/重建本地 SQLite 的第 1 層表
(2) 爬  ：Playwright 爬 19 家影城 → 寫本地 SQLite 的第 2 層
          （showtimes / crawl_runs / raw_pages）
(3) 匯出：export_geojson.py 以「第 1 層(來自控制面) + 第 2 層(剛爬的)」
          產出 locations.geojson → git push
(4) 回寫：把 crawl_runs 狀態、統計數字（爬到幾家/幾場/幾筆失敗）、
          log 摘要，透過 API 回寫控制面 Postgres
```

**同步鐵律**：

- 資料流是**單向環**：Curated 只從 Postgres 流向 SQLite；Crawled 狀態只從 SQLite 流向 Postgres。沒有任何路徑讓爬蟲面的資料回頭覆蓋 Postgres 的第 1 層。
- 每次執行的第 (1) 步都是**整份重拉**（資料量小：數十品牌 × 上百據點），不做增量同步——簡單勝於聰明，也天然消除漂移。
- SQLite 視為**可拋棄**：損毀、格式不合、schema 升級，一律刪掉重建，不修復。

### 5.4 GeoJSON 資料契約

- `web/data/locations.geojson` 維持現有格式（多電影單一 payload、前端下拉切換），是公開地圖與後台的**共同契約**。
- 後台的「地圖預覽」功能直接讀同一份 GeoJSON 產出邏輯（同一支 `export_geojson.py` 的函式），確保後台看到的與公開地圖一致。

---

## 6. 權限與稽核設計

### 6.1 角色定義（定案 D4）

僅兩種角色，直接對應 Django 的 Group 機制：

| 角色 | 對象 | 定位 |
| --- | --- | --- |
| **管理員 Admin** | 系統擁有者 | 管人、管系統、管爬蟲觸發 |
| **編輯者 Editor** | 協作同事 | 管內容（影城資料、追蹤電影） |

### 6.2 權限矩陣

| 功能 | 管理員 | 編輯者 |
| --- | :---: | :---: |
| 使用者管理（建帳號、改角色、停用） | ✅ | ❌ |
| 系統設定（GitHub token、runner 設定、匯出參數） | ✅ | ❌ |
| 觸發爬蟲（按鈕 → workflow_dispatch） | ✅ | ❌ |
| 查看爬蟲狀態 / crawl_runs / log | ✅ | ✅ |
| 編輯影城品牌（chains：名稱、URL、logo） | ✅ | ✅ |
| 編輯影城據點（locations：地址、經緯度、display_name） | ✅ | ✅ |
| 編輯追蹤電影（movies、movie_targets） | ✅ | ✅ |
| 地圖預覽 | ✅ | ✅ |
| 查看稽核紀錄 | ✅ | ✅（唯讀） |

> 註：管理員隱含具備編輯者的所有權限。

### 6.3 稽核設計

1. **行級稽核欄位**：所有第 1 層（Curated）的表一律加上四個欄位：

   | 欄位 | 型別 | 說明 |
   | --- | --- | --- |
   | `created_by` | FK → users | 建立者 |
   | `created_at` | timestamptz | 建立時間 |
   | `updated_by` | FK → users | 最後修改者 |
   | `updated_at` | timestamptz | 最後修改時間 |

   由 Django model 層自動填入（覆寫 `save()` 或以 middleware 取當前使用者），表單上不可手動指定。

2. **變更歷程（audit log 表）**：另設一張 `audit_log`，記錄「誰、何時、對哪張表哪筆資料、哪個欄位、從什麼值改成什麼值」。第一版可用 Django 生態的現成方案（如 django-simple-history 或等效自寫 signal），重點是**每筆修改可回溯**。
3. **爬蟲寫入的歸屬**：爬蟲面回寫 crawl_runs 時使用專屬的 service 帳號（如 `crawler-bot`），在稽核上與真人操作清楚區分。

---

## 7. 爬蟲觸發機制

### 7.1 機制總述（定案 D2）

後台按鈕不直接跑爬蟲，而是**透過 GitHub 當中介**：Django 呼叫 GitHub REST API 觸發 `workflow_dispatch`，GitHub Actions 把工作派給 self-hosted runner（使用者的 Windows），爬完後由 runner 上的腳本回寫狀態給控制面。

好處：

- 控制面主機**不需要** Playwright、瀏覽器、大量記憶體——維持 $5~7/月方案可行。
- 爬蟲從**台灣 IP** 出發，避免影城網站 geo-block。
- GitHub Actions 免費提供了排程（cron）、重試、workflow log、併發鎖等基礎設施，不必自建 job queue。

### 7.2 時序（Sequence）

```
 編輯者/管理員      Django 控制面        GitHub API/Actions    self-hosted runner     Postgres
     │                  │                      │                （Windows）              │
 (1) │──按「更新地圖」──▶│                      │                      │                  │
 (2) │                  │─ 建 crawl_run(狀態=  │                      │                  │
     │                  │   queued, 產生       │                      │                  │
     │                  │   run_token) ────────┼──────────────────────┼─────────────────▶│
 (3) │                  │─ POST /dispatches ──▶│                      │                  │
     │                  │   (inputs: run_id,   │                      │                  │
     │                  │    movies, chains)   │                      │                  │
 (4) │                  │                      │── 派工（長輪詢）────▶│                  │
 (5) │                  │◀─────────────────────┼──── PATCH 狀態=running（帶 run_token）──▶│
 (6) │                  │                      │                      │─ a.拉 Curated    │
     │                  │◀────────────────────────────────────────────│   GET /api/     │
     │                  │                      │                      │   curated-export │
     │                  │                      │                      │─ b.Playwright 爬 │
     │                  │                      │                      │─ c.export_geojson│
     │                  │                      │◀── d. git push ──────│                  │
 (7) │                  │◀─────────────────────┼──── PATCH 狀態=success/failed           │
     │                  │                      │      + 統計 + log 摘要 ────────────────▶│
 (8) │◀─儀表板顯示結果──│（輪詢或頁面刷新）     │                      │                  │
     │                  │                      │── Pages 自動部署 ──▶ 公開地圖更新        │
```

### 7.3 各步驟設計要點

| 步驟 | 要點 |
| --- | --- |
| (2) 建 crawl_run | 控制面先落地一筆 `crawl_runs`（狀態 `queued`），取得 `run_id`，並產生一次性的 `run_token` 供該次執行回寫時驗證。 |
| (3) workflow_dispatch | Django 以 fine-grained GitHub token 呼叫 `POST /repos/{owner}/{repo}/actions/workflows/{id}/dispatches`，`inputs` 帶 `run_id` 與可選過濾（指定電影/品牌）。 |
| (4)(5) runner 接工 | workflow 指定 `runs-on: [self-hosted, windows, crawler]`。第一步即回報 `running`，讓後台儀表板即時反映。 |
| (6) 執行 | 依 5.3 節四步驟：拉 → 爬 → 匯出 → push。push 用 workflow 內建的 `GITHUB_TOKEN` 或 deploy key，不用個人帳號。 |
| (7) 回寫 | 無論成敗都要回寫（workflow 的 `if: always()` step）：狀態、耗時、各影城成功/失敗數、log 末段摘要。完整 log 留在 GitHub Actions，後台提供連結跳轉。 |
| 逾時保護 | 控制面對 `queued`/`running` 超過閾值（如 45 分鐘）的 run 自動標記 `timeout`，避免儀表板卡在殭屍狀態（runner 關機、網路中斷時會發生）。 |
| 併發控制 | workflow 設 `concurrency` group，同一時間只允許一個爬蟲 run；後台在有 run 進行中時停用觸發按鈕。 |
| 排程 | 除了手動按鈕，同一支 workflow 可加 `schedule`（cron）做每日自動更新，兩種觸發共用同一條路徑。 |

---

## 8. 部署拓撲

### 8.1 各元件位置

| 元件 | 部署位置 | 方案/成本 | 常駐性 |
| --- | --- | --- | --- |
| Django 後台 | 雲端 PaaS（候選：Railway / Fly.io） | 免費層或 $5~7/月 | 常駐 |
| Postgres | 同平台附帶，或獨立用 Neon 免費層 | 免費層起 | 常駐 |
| GitHub Actions workflow | GitHub（repo 內 `.github/workflows/`） | 免費（self-hosted 不計分鐘數） | 按需 |
| self-hosted runner | 使用者現有 Windows 機器 | $0（現有硬體） | 開機時在線 |
| 公開地圖 | GitHub Pages | 免費 | 常駐（靜態） |

### 8.2 拓撲圖

```
        ┌──────────────── 雲端 ────────────────┐
        │  PaaS (Railway/Fly.io)               │
        │  ┌────────────┐   ┌───────────────┐  │
        │  │ Django App │──▶│ Postgres      │  │
        │  │ (HTTPS)    │   │ (Neon 或同站) │  │
        │  └─────┬──────┘   └───────────────┘  │
        └────────┼──────────────────▲──────────┘
                 │ GitHub API       │ HTTPS API（拉 Curated / 回寫狀態）
                 ▼                  │
        ┌─────────────────┐         │
        │     GitHub      │         │
        │ Actions + repo  │         │
        │ + Pages(公開圖) │         │
        └────────┬────────┘         │
                 │ runner 長輪詢     │
                 │ (outbound only)  │
        ┌────────▼─────────────────┴──────────┐
        │  使用者的 Windows（台灣、住宅網路）    │
        │  - GitHub Actions self-hosted runner │
        │  - Python + Playwright（現成環境）    │
        │  - 工作用 SQLite（可拋棄快取）         │
        └──────────────────────────────────────┘
```

### 8.3 網路連線特性

- **Windows 機器不需要對外開任何 port**：runner 是 outbound 長輪詢連 GitHub；回寫控制面也是 outbound HTTPS。家用網路 NAT 後即可運作，無固定 IP 需求。
- 控制面只暴露一個 HTTPS 入口（後台網頁 + 少量 API endpoint），Postgres 不對公網開放（走平台內網或連線白名單）。
- 憑證分佈：
  - Django 環境變數：Postgres 連線字串、GitHub fine-grained token（僅 workflow dispatch 權限）、Django SECRET_KEY。
  - GitHub repo secrets：控制面 API 的 service token（供 runner 回寫用）。
  - Windows runner：只持有 GitHub 發的 runner 註冊憑證，不長期保存其他密鑰。

---

## 9. 對外整合出口

公開地圖之外，保留三種對外整合方式，由淺入深：

| 出口 | 形式 | 適用情境 | 現況 |
| --- | --- | --- | --- |
| 1. 連結跳轉 | 直接分享 GitHub Pages URL（可帶查詢參數指定電影/視角） | 社群貼文、訊息分享 | 已可用 |
| 2. iframe 嵌入 | `<iframe src="https://…/index.html?...">` 嵌入他人網站/部落格 | 合作方想在自己頁面內顯示地圖 | 已可用（需確認頁面無反嵌入 header） |
| 3. API 串接 | 控制面提供唯讀 JSON API（或直接取用 repo 內的 `locations.geojson` raw URL） | 程式化取用場次/據點資料 | 規劃中（見第 11 章） |

設計原則：前兩種出口零後端成本，依附靜態站存在；第三種出口等控制面穩定後再開，且一律**唯讀、免登入、可加 rate limit**，不與後台管理 API 混用同一組 endpoint 權限。

---

## 10. 風險與待驗證項

| # | 風險/待驗證項 | 說明 | 緩解/驗證方式 |
| --- | --- | --- | --- |
| R1 | **Postgres ↔ SQLite 同步實作** | 「整份重拉重建」在 schema 演進時（欄位增減）兩端要同步改，可能漂移。 | Curated 匯出 API 帶 schema 版本號；爬蟲面啟動時先檢查版本相容，不合即失敗並回報，不強行執行。首次實作先以一部電影、一家影城端到端驗證。 |
| R2 | **self-hosted runner 安全性** | runner 會執行 repo 的 workflow 定義；若 repo 為 public，外部 PR 觸發 workflow 有在使用者機器上執行任意程式碼的風險。 | 限制 runner 僅接受指定 workflow；關閉 fork PR 觸發（`workflow_dispatch` + `schedule` only）；GitHub 設定「需 approval 才能在 self-hosted 跑外部貢獻者 workflow」；runner 以低權限 Windows 帳號執行。此項**上線前必須逐條驗證**。 |
| R3 | **爬蟲面對控制面的存取憑證管理** | runner 回寫狀態與拉 Curated 資料需要 API token；token 洩漏等於可寫 crawl_runs、可讀全部據點資料。 | token 存 GitHub repo secrets（不落地 Windows 磁碟）；權限最小化（僅 curated-export 讀 + crawl_runs 寫）；搭配每次 run 的一次性 `run_token` 綁定單次回寫；定期輪換。 |
| R4 | **GitHub token 權限範圍（控制面側）** | Django 觸發 workflow_dispatch 用的 token 若給到 repo 全權限，被竊即可改 code、改 Pages。 | 使用 fine-grained PAT，僅授 `actions: write`（單一 repo）；不授 contents 權限；token 只存於 PaaS 環境變數。 |
| R5 | **runner 在線可用性** | 爬蟲依賴使用者 Windows 開機且 runner 服務在跑；關機/休眠/斷網時按鈕會排隊或逾時。 | runner 裝成 Windows 服務（開機自啟、防休眠）；控制面儀表板顯示 runner 在線狀態（GitHub API 可查）；佇列逾時自動標記（見 7.3）。 |
| R6 | **免費層限制** | Neon/Railway/Fly.io 免費層有休眠、連線數、流量限制，可能影響後台體驗。 | 先在免費層 PoC，量測冷啟動時間；不可接受再升 $5~7 方案（已在預算內）。 |
| R7 | **影城網站改版** | 19 家爬蟲任一家改版即部分失敗。 | crawl_runs 記錄逐影城成敗；部分失敗不阻擋整體匯出（沿用上次成功資料並在後台標示過期）；raw_pages 快照輔助除錯。 |
| R8 | **資料遷移一次性風險** | SQLite → Postgres 遷移時 override 修正、既有 8 表資料要無損搬遷。 | 遷移腳本先套 `manual_location_overrides.sql` 再匯出；遷移後以筆數與抽樣比對驗收；SQLite 原檔保留封存。 |

---

## 11. 未來演進

依價值與依賴順序排列，**皆不在第一版範圍**：

1. **BAT 邏輯 Python 化為 management command**
   把 `更新地圖.bat` 中「跑更新 + git add/commit/push」的流程改寫為 Django management command（或爬蟲面的純 Python 腳本），供 workflow 直接呼叫。BAT 保留為本機手動備援入口，內容縮減為呼叫該 command。消除 Windows-only 的 shell 邏輯，錯誤處理與 log 統一進 Python。

2. **電影清單 txt → DB**
   `電影清單.txt` 退役，追蹤電影完全以控制面的 `movies` + `movie_targets` 為準，由後台介面維護（編輯者權限即可）。爬蟲面在「拉 Curated」步驟取得清單。txt 檔封存不再讀取。

3. **API 化（第三整合出口落地）**
   控制面開唯讀公開 API：`GET /api/v1/movies`、`GET /api/v1/movies/{id}/locations`（回 GeoJSON）。公開地圖屆時**可選擇**改讀 API 取得更即時的資料，但靜態 GeoJSON 路徑保留為 fallback——公開地圖永不因控制面故障而全掛。

4. **更遠期的可能性**（記錄備查，不承諾）
   - 據點爬蟲（`fetch_*_locations.py` 系列）納入同一 workflow，差異以「提示待人工確認」呈現（見 5.2-4）。
   - crawl_runs 失敗自動通知（email / LINE Notify）。
   - 稽核紀錄的差異視覺化（before/after diff 檢視）。

---

## 附錄 A：名詞對照

| 名詞 | 意義 |
| --- | --- |
| 控制面 Control Plane | 雲端 Django + Postgres，管人、管資料、管觸發 |
| 爬蟲面 Crawl Plane | GitHub Actions self-hosted runner（使用者 Windows），實際執行爬蟲與匯出 |
| Curated | 第 1 層人工權威資料，只有人能改 |
| Crawled | 第 2 層爬蟲產出資料，可拋棄重爬 |
| Derived | 第 3 層衍生輸出（GeoJSON/KML），可隨時重新匯出 |
| 人工永遠贏 | 任何自動化流程都不得覆寫人工維護的欄位；衝突呈現給人裁決 |
| run_token | 每次爬蟲 run 產生的一次性憑證，用於驗證該次的狀態回寫 |
