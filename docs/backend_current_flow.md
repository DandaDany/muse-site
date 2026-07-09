# 後台化 Phase 0：現有「一鍵更新」流程盤點

> 目的：讓之後要把這條半自動流程改成後台服務的人，不用翻程式碼就能看懂目前每個環節的輸入、輸出與失敗點。
> 撰寫日期：2026-07-09。本文只描述「現況」，不含建議做法。凡是讀不到、無法確認的地方一律標「待確認」。
> 資料來源：實際精讀專案內檔案，非臆測。

---

## 0. 總覽（一句話）

使用者在 Windows 上雙擊 `更新地圖.bat` → 執行 `scripts/update_map.py`（讀 `電影清單.txt`，對每部電影跑一次場次爬蟲，再匯出前端 GeoJSON）→ bat 接著 `git add / commit / push` → GitHub Actions 自動把 `web/` 部署到 GitHub Pages。

整條鏈路綁定 Windows、需要本機瀏覽器（Playwright / 部分來源甚至需要「有畫面」的 Chrome）、需要本機 Git 憑證，且執行時間長（逐部電影 × 18 條來源，且多條需開瀏覽器）。

---

## 1. 電影清單.txt（追蹤電影清單）

| 項目 | 內容 |
|---|---|
| 絕對路徑 | `/home/user/muse-site/電影清單.txt`（Windows 上即專案根目錄下的 `電影清單.txt`） |
| 檔名 | `電影清單.txt`（中文檔名） |
| 編碼 | 以 `utf-8-sig` 讀取（`read_movie_titles` 用 `encoding="utf-8-sig"`，可容忍 BOM） |
| 內容 | 可多部，一行一部，前面有編號 |
| 是否有別名 | 檔案格式**不支援別名**（別名只能靠 `fetch_movie_showtimes.py --alias` 或程式內建，`update_map.py` 不會傳別名） |
| 是否有日期 | **無**，日期不寫在清單檔，由 `--date` 統一決定 |

目前實際內容（兩部）：

```text
1. 玩具總動員5
2.名偵探柯南:高速公路的墮天使
```

### `update_map.py` 如何解析（`read_movie_titles`）

`/home/user/muse-site/scripts/update_map.py` 第 15–25 行：

```python
title = re.sub(r"^\s*\d+\s*[.)、]\s*", "", raw_line).strip()
if not title or title.startswith("#"):
    continue
if title not in seen:
    titles.append(title)
    seen.add(title)
```

- **去編號**：正則 `^\s*\d+\s*[.)、]\s*` 會移除行首的 `1.`、`2、`、`3)`（含有無空白皆可，例如第 2 行 `2.名偵探柯南...` 沒空白也能正確去除）。
- **去註解 / 空行**：去除後為空、或以 `#` 開頭的行會被略過。
- **去重**：用 `seen` 集合，同名只留一筆。
- **保留順序**：依檔案出現順序。
- 若解析後一部都沒有 → `raise SystemExit(...)`（非零離開，bat 會判定失敗）。

> 注意：標題內的冒號、破折號等會**原樣保留**（`名偵探柯南:高速公路的墮天使` 冒號不會被去掉），這個字串會被當成資料庫 `movies.title` 的正式標題，也會傳給爬蟲與匯出。

---

## 2. 更新地圖.bat（一鍵入口）

| 項目 | 內容 |
|---|---|
| 絕對路徑 | `/home/user/muse-site/更新地圖.bat` |
| 平台 | **Windows 專用**（`@echo off` / `setlocal` / `errorlevel` / `pause` / `py -3` 都是 Windows CMD 語法） |
| cwd 設定 | `cd /d "%~dp0"`＝切到 bat 所在目錄（專案根） |
| Python 啟動器 | `py -3 scripts\update_map.py`（Windows py launcher，指定 Python 3） |
| Git 路徑 | 先試 `%LOCALAPPDATA%\Programs\Git\cmd\git.exe`，不存在則退回 PATH 上的 `git` |

### 依序執行的步驟與成功/失敗判斷

| 步驟 | 指令 | 失敗處理 |
|---|---|---|
| 1 | `py -3 scripts\update_map.py` | `if errorlevel 1` → 印 `[ERROR] Update failed.` → `pause` → `exit /b 1` |
| 2 | `git add .` | errorlevel≠0 → `[ERROR] git add failed.` → pause → exit 1 |
| 3 | `git diff --cached --quiet` | **若沒有變更**（errorlevel 0）→ 印 `[DONE] ... no Git changes to publish` → pause → `exit /b 0`（正常結束，不 commit/push） |
| 4 | `git commit -m "Update map data"` | 失敗 → `[ERROR] git commit failed.` → pause → exit 1 |
| 5 | `git push` | 失敗 → `[ERROR] git push failed.` → pause → exit 1 |
| 6 | 印 `[DONE] Map data updated and pushed...` | `pause` |

- **有 `pause`**：每個分支（成功或失敗）都會 `pause`，等使用者按鍵 → 這是為互動式桌面設計，後台無人值守會卡住。
- **最後有 `git add / commit / push`**：commit 訊息固定為 `"Update map data"`；push 用預設 remote/branch（未指定）。
- **提交範圍是 `git add .`（整個工作目錄）**，不是只加 `web/`；靠 `.gitignore` 把 SQLite、`data/output/*` 等擋掉（見第 5、9 節）。

---

## 3. 完整呼叫鏈（bat → update_map → fetch → export）

```
更新地圖.bat
  └─ py -3 scripts/update_map.py                (cwd = 專案根)
        ├─ read_movie_titles(電影清單.txt)       解析出 movie_titles[]
        │
        ├─ 對每一部電影 movie_title：
        │     subprocess: python scripts/fetch_movie_showtimes.py "<movie_title>" --date <date>
        │        （cwd = PROJECT_DIR，check=True）
        │
        └─ 全部電影抓完後，一次匯出：
              subprocess: python scripts/export_geojson.py --date <date>
                            --movie-title "<電影1>" --movie-title "<電影2>" ...
  └─ git add . / commit / push
```

### 參數與預設

| 參數 | 位置 | 預設 | 說明 |
|---|---|---|---|
| `--movie-list` | update_map.py | `電影清單.txt` | 可換清單檔；相對路徑會接到專案根 |
| `--date` | update_map.py | `date.today().isoformat()`（執行當天） | 會**原樣往下傳**給 fetch 與 export |
| `movie_title`（位置參數） | fetch_movie_showtimes.py | 無（必填） | 由 update_map 逐部帶入 |
| `--date` | fetch_movie_showtimes.py | 今天 | update_map 會顯式帶入 |
| `--alias`（可重複） | fetch_movie_showtimes.py | 空 | **update_map 不會傳**；只有手動執行才有 |
| `--keep-existing` | fetch_movie_showtimes.py | 關（預設會先刪當天資料） | **update_map 不會傳** → 每次重跑都會清掉當天該片場次再重寫（見第 7 節） |
| `--db` | fetch / export / init | `data/movie_map.sqlite` | |
| `--movie-title`（可重複） | export_geojson.py | 空 | update_map 會把清單全部帶入 |

`run_step` 用 `subprocess.run([sys.executable, *args], cwd=PROJECT_DIR, check=True)`：**任一子步驟非零離開就會拋 `CalledProcessError`，讓 update_map 崩潰、bat 收到 errorlevel≠0**。但注意 `fetch_movie_showtimes.py` 內部把每個來源失敗都 try/except 吃掉了，正常情況回傳 0（見第 9 節「失敗被吞」）。

---

## 4. 輸入檔

| 輸入 | 路徑 | 用途 | 進 Git？ |
|---|---|---|---|
| 電影清單 | `/home/user/muse-site/電影清單.txt` | 決定要抓哪些電影 | 是 |
| 影城品牌來源 | `/home/user/muse-site/data/input/cinema_sources.csv` | 品牌 official/crawl URL、`all_locations_assumed_showing`、notes 等（14 欄表頭） | 是 |
| 威秀/MUVIE 據點 | `/home/user/muse-site/data/input/vieshow_locations.csv` | 威秀與 MUVIE 據點與影城代碼 | 是 |
| 手動補充 URL | `/home/user/muse-site/data/input/manual_location_urls.csv` | 特定據點入口 URL、`source_location_code` | 是 |
| SQLite 既有資料 | `/home/user/muse-site/data/movie_map.sqlite` | 影城/據點/經緯度/既有場次 | **否（.gitignore 排除）** |

> 重要：這些 CSV 是「建立影城與據點」的匯入來源（README 的 `import_cinema_sources.py`、`fetch_*_locations.py`、`geocode_locations.py` 等），**不在一鍵更新流程內**。一鍵更新只做「抓場次 + 匯出」，前提是 SQLite 內已經有 `cinema_chains` / `cinema_locations`（含經緯度、`source_location_code`）。
> 目前 repo 內**沒有** commit 的 `.sqlite` 檔（已確認 `data/*.sqlite` 被 gitignore）。也就是說一鍵更新**高度依賴本機那顆未進版控的 SQLite**（見第 9、10 節）。

---

## 5. 輸出檔

### 5.1 SQLite（`data/movie_map.sqlite`）

`fetch_movie_showtimes.py` 每次執行會寫：

| 表 | 寫入內容 |
|---|---|
| `movies` | 若 `title` 不存在則 `INSERT`（notes 記「由 fetch_movie_showtimes.py 建立」，active=1）；存在則取回 id |
| `crawl_runs` | **每個來源一列**：開始時 insert（run_type=`showtimes`、status=`running`），結束時 update 成 `success`/`failed` 並記 `rows_found`/`rows_saved`/`error_message` |
| `showtimes` | 解析到的每一筆場次（upsert，見第 7 節） |
| `raw_pages` | schema 有這張表，但一鍵流程的爬蟲**未寫入**（原始頁面改存檔案，見 5.2）；待確認是否其他腳本才用 |

`export_geojson.py` 與所有腳本開頭都會呼叫 `init_db()`：確保 `sql/schema.sql` 已套用並跑過 `MIGRATIONS`（目前 migration 只補 `cinema_locations.source_location_code`、`cinema_locations.notes` 兩欄）。

### 5.2 原始回應快取

- 路徑：`/home/user/muse-site/data/output/showtimes/`
- 命名：`{台北時間 YYYYMMDD_HHMMSS}_{來源安全名}.{json|html}`（`save_raw`）
- 內容：各來源的原始 JSON / HTML（例如 `..._skcinemas_sessions_<id>.json`、`..._ambassador_<id>.html`、`..._vieshow_<code>.html`）
- **被 .gitignore 排除**（`data/output/*`，只留 `.gitkeep`）

### 5.3 前端 GeoJSON

- 路徑：`/home/user/muse-site/web/data/locations.geojson`（`export_geojson.py` 的 `DEFAULT_OUTPUT`）
- 由 `update_map.py` 以「帶 `--movie-title` 清單」的模式產生 → payload 含：
  - `type` / `name`＝`木棉花電影全台上映地圖`
  - `movies`：每部電影的 `title`/`show_date`/`feature_count`
  - `movie_features`：`{片名: features[]}`（前端下拉切換用）
  - `features`：**只放清單第一部電影**的 features（top-level）
  - `feature_count`、`generated_at`（今天）、`movie_title`（第一部）、`show_date`
- **會進 Git**（在 `web/` 底下），bat push 後 GitHub Pages 部署。
- 只輸出「有場次、且有經緯度、且 movie/location/chain 皆 active」的影城點；同一據點多場次會 group 成一個 point，`showtimes[]` 列出時間/格式/語言/影廳。

### 5.4 KML（不在一鍵流程）

- `scripts/export_kml.py`：預設輸出到 `/home/user/muse-site/data/output/kml/`（被 gitignore）。
- **`更新地圖.bat` 與 `update_map.py` 都沒有呼叫 export_kml**。KML 是 README 記載的手動指令（`python scripts/export_kml.py [--movie-title ...] [--date ...]`），供匯入 Google My Maps 用。`schema.sql` 有 `kml_exports` 表對應。

---

## 6. 日期處理

- 三支腳本（update_map / fetch / export）的 `--date` 預設都是 `date.today().isoformat()`＝**執行當天**（本機系統日期）。
- **可指定**：手動 `python scripts/fetch_movie_showtimes.py "片名" --date 2026-06-26`；但 `更新地圖.bat` **寫死用今天**（bat 不接受參數、update_map 不帶 `--date`）。
- **時區**：程式定義 `TAIPEI = ZoneInfo("Asia/Taipei")`，用在：
  - `save_raw` 檔名時間戳（台北時間）。
  - 秀泰 API 把 `startedAt`（UTC）轉台北時間再取 `%H:%M`。
- 但 `--date` 的「今天」是取本機 `date.today()`（依作業系統時區），**不是強制台北**。若後台跑在 UTC 主機，跨午夜時「今天」可能與台灣差一天 → 待留意。

---

## 7. 是否覆蓋舊資料（去重 / 重跑行為）

兩層機制：

1. **執行前整批清除**（預設）：`fetch_movie_showtimes.py` main 內，若沒帶 `--keep-existing` → `clear_existing()`：
   ```sql
   DELETE FROM showtimes WHERE movie_id = ? AND show_date = ?
   ```
   → **同一部電影、同一天，重跑會先刪光既有場次再重寫**。`更新地圖.bat` 走的就是這條（不帶 `--keep-existing`）。

2. **寫入時 upsert 去重**：`showtimes` 有唯一索引 `ux_showtimes_identity`：
   ```
   (movie_id, location_id, show_date, start_time,
    ifnull(format,''), ifnull(language,''), ifnull(subtitle,''), ifnull(booking_url,''))
   ```
   `save_showtimes` 用 `ON CONFLICT(...) DO UPDATE`：同一識別鍵的場次會更新 `crawl_run_id`/`auditorium`/`source_url`/`raw_text`，不會重複插入。

**重跑會發生什麼**：先刪掉今天該片全部場次 → 逐來源重新抓 → 抓成功的來源重新寫回；**若某來源這次連不上或改版抓 0 筆，該來源前一輪的場次不會被保留**（已在步驟 1 被刪，且步驟 2 沒有新資料補回）。也就是「重跑＝以本次抓到的為準，全覆蓋」。

---

## 8. 爬蟲來源現況（一鍵流程實際接入的 18 條 / 19 家）

`fetch_movie_showtimes.py` 的 `sources` 清單依序執行以下 **18 個 fetcher**（其中威秀那條同時涵蓋威秀＋MUVIE 兩個品牌，故 README 稱「19 個影城系統」）。每條各自 `try/except` 隔離，互不影響。

| # | 來源（chain_name） | 取得方式 | 需 Playwright？ | SSL | 穩定度標註 |
|---|---|---|---|---|---|
| 1 | 威秀影城 / VIESHOW ＋ MUVIE CINEMAS | Playwright 開頁、下拉選單選 code、解析 HTML 文字塊 | **是，且 `headless=False`（要有畫面的 Chrome，`slow_mo=200`）** | 預設驗證 | 待驗證；有 `Access Denied` 偵測會直接丟例外 |
| 2 | 秀泰影城 | 官方 bootstrap JSON API (`capi.showtimes.com.tw/4/app/bootstrap`) | 否 | 驗證 | 相對穩定（結構化 API） |
| 3 | 國賓影城 | `ambassador.com.tw/home/Showtime` HTML，BeautifulSoup `.showtime-item` | 否 | 驗證 | 相對穩定（結構化 HTML） |
| 4 | 新光影城 | Playwright 擷取短效 headers（timestamp/DID/token）→ 呼叫 `GetSessionByCinemasIDForApp` | **是（headless=True，抓 API headers）** | 驗證 | 依賴短效 header，較脆 |
| 5 | in89 豪華影城 | 從據點頁抓 `theater_api` host → 呼叫 `getStagesByDate` JSON | 否（純 HTTP） | **關閉（verify_ssl=False）** | 有 fallback host 表，較脆 |
| 6 | 喜樂時代影城 | Playwright 渲染頁面 → 通用文字塊解析 | **是（headless=True）** | 驗證 | 待驗證（通用文字解析） |
| 7 | 美麗新影城 | Timetable 頁內 `var CinemaList='...'` JSON | 否 | 驗證 | 相對穩定（結構化 JSON） |
| 8 | 天台影城 | index HTML → 通用文字塊解析 | 否 | **關閉** | 待驗證 |
| 9 | 威尼斯影城 | Playwright 渲染 showtime.php（翻 4 頁）→ 文字塊解析 | **是（headless=True）** | 驗證 | 待驗證 |
| 10 | 親親影城 / 親親戲院 | `ccmovie.com.tw` HTML，依 `show_date` 找 tab | 否 | 驗證 | 相對穩定（第一版已接上） |
| 11 | 王牌映画影城 | `acecinema.com.tw/movie/now` HTML `.movie_list` | 否 | 驗證 | 相對穩定（第一版已接上） |
| 12 | 環球中華影城 | `uch-movies.tw/time.aspx` HTML → 文字塊解析 | 否 | **關閉** | 待驗證 |
| 13 | 百老匯影城 | `GetMovieList/{code}` JSON API | 否 | **關閉** | parser 已加入，待連線驗證 |
| 14 | 高雄環球影城 | `u-movie.com.tw` HTML → 正則抓時間/廳 | 否 | 驗證 | 待驗證（含 `Toy Story 5` 字串硬寫） |
| 15 | 中影屏東影城 | `ptcinema...time?date=` HTML → 逐 lightbox 詳情頁 | 否 | **關閉** | 待驗證 |
| 16 | 新月豪華影城 | `lunacinemax.com.tw` HTML → 逐行解析 | 否 | 驗證 | parser 已加入，待驗證 |
| 17 | 日新戲院 / 宜蘭電影資訊網 | `ilanmovie.com` HTML 表格 | 否 | 驗證 | parser 已加入，待驗證 |
| 18 | 金獅影城 | Playwright 渲染 `cinemax.windlion.com.tw` → 逐行解析 | **是（headless=True）** | 驗證 | 待驗證；含 `2026-06-26(五)` 日期字串硬寫 |

**尚未接入一鍵流程**（README 提到但 sources 清單裡沒有獨立 fetcher）：新光已接（#4）；但 README 舊句「威秀/MUVIE 與新光需再補專門場次 API」與現況不完全一致（見第 11 節）。

**需要瀏覽器的來源共 5 條**：#1 威秀（唯一需要**有畫面**的 Chrome）、#4 新光、#6 喜樂時代、#9 威尼斯、#18 金獅（後四者 headless）。

**SSL 驗證關閉的來源**：#5 in89、#8 天台、#12 環球中華、#13 百老匯、#15 中影屏東（`verify_ssl=False`，用 `ssl._create_unverified_context()`）。

### 電影比對邏輯（跨來源共用）
`normalize_text` 會：全形數字轉半形、英文轉小寫、移除空白與常見標點；`movie_matches` 判斷任一別名正規化後是否為文字子字串。內建別名僅對 `玩具總動員5`（自動加 `Toy Story 5`、`玩具總動員５`、`玩具總動員 5`）。**其他電影（例如清單裡的「名偵探柯南:高速公路的墮天使」）沒有內建英/日文別名**，只能靠標題本身比對 → 若來源用不同寫法可能漏抓（風險，見第 9 節）。

---

## 9. 可能失敗點

| 類別 | 具體風險 |
|---|---|
| 網路 / 逾時 | 全部 HTTP 逾時 45 秒；Playwright goto 45–60 秒 + 額外 `wait_for_timeout` 數秒。來源慢或斷線 → 該來源 `crawl_runs` 記 `failed`，但**整支腳本仍回傳 0** |
| geo-block / 反爬 | 威秀有 `Access Denied` 偵測會**丟 RuntimeError**（但被 run_source 的 try/except 接住，只記該來源 failed）；海外 IP 可能被更多來源擋 |
| Playwright 環境 | 需已 `playwright install chromium`。**威秀用 `headless=False`＝需要桌面/顯示器**，在無頭伺服器會失敗（需 Xvfb 之類）。新光靠 7 秒內攔到短效 header，攔不到就 `RuntimeError("Could not capture ... headers")` |
| 來源改版 | 大量 fetcher 靠 HTML class 名 / 正則 / 文字塊；來源改版就抓 0 筆。多處有**硬寫的當期字串**：`fetch_windlion` 的 `"2026-06-26(五)"`、`fetch_umovie` 移除 `"Toy Story 5"` → 換片/換日可能失準 |
| 失敗被吞（重要） | `run_source` 把每個來源例外 `try/except` 成 `failed` 並 `continue`；`main()` 最後只 `print` 失敗清單，**不 `sys.exit(非零)`**。因此只要腳本本身沒崩，`fetch_movie_showtimes.py` 回傳 0 → `update_map.py` check=True 不會擋 → **bat 的 errorlevel 判斷不到「部分來源失敗 / 全部抓 0 筆」**，仍會照常 commit/push（可能 push 出一份空/缺料的地圖） |
| SQLite 未進 Git | `data/movie_map.sqlite` 被 gitignore。流程**假設本機已有建好的影城/據點資料庫**；換機器、重灌、CI 乾淨環境都沒有這顆 DB → 抓到的場次會因 `get_locations` 查無據點而落空 |
| 別名不足 | 非「玩具總動員5」的電影沒有內建別名，靠標題原字串比對，來源寫法不同就漏抓 |
| 日期時區 | `date.today()` 依主機時區，非強制台北；跨午夜可能差一天 |
| bat 為 Windows-only | `py -3`、`errorlevel`、`pause`、`%LOCALAPPDATA%` git 路徑全是 Windows 語法；Linux/mac 無法直接跑 |
| Git 權限 | `git push` 需本機已設定好 remote 與可用憑證（HTTPS token / SSH key）；憑證失效或無 upstream → push 失敗（bat 會 pause 卡住） |
| 互動卡住 | 每個結束分支都 `pause`，需人按鍵；無人值守會永遠卡在 pause |
| `git add .` 範圍 | 是整個工作目錄；一旦 `.gitignore` 沒擋好（例如新產物），可能把本機私有檔或大檔一起 commit/push |

---

## 10. 後台安全呼叫評估（若要被後台程式直接呼叫）

現況這條流程要被後台服務呼叫，前提與風險如下：

**硬性前提**
1. **Windows 綁定**：`更新地圖.bat` 無法在 Linux 後台直接執行。若要後台化，需改為直接呼叫 `python scripts/update_map.py` 並自行處理 git（繞開 bat）。
2. **需要瀏覽器，且威秀需要「有畫面」**：`fetch_vieshow` 是 `headless=False`。無頭伺服器需 Xvfb / 虛擬顯示，否則威秀會失敗；其餘 Playwright 來源為 headless=True，仍需安裝 Chromium。
3. **需要既有 SQLite**：`data/movie_map.sqlite` 不在版控。後台環境必須先具備一份已匯入影城/據點（含經緯度、`source_location_code`）的 DB，否則場次抓到也無處落點。
4. **需要 Git 憑證**：若沿用 bat 的 push 行為，後台需可存取 remote 的可用憑證，且分支/upstream 已設定。

**執行特性風險**
5. **同步、耗時長**：逐部電影 × 18 條來源，且 5 條開瀏覽器（含多個 `wait_for_timeout` 數秒、威尼斯翻 4 頁）→ 單次可能數分鐘以上。後台若同步等待需設足夠 timeout，且不宜高頻併發（會對來源站台造成壓力、也可能觸發反爬）。
6. **無可靠的成功/失敗訊號**：如第 9 節，部分或全部來源失敗時流程仍回傳 0。後台無法只靠 exit code 判斷資料品質，需**改讀 `crawl_runs`（status/rows_saved）或比對 `showtimes` 筆數**才能判斷本次是否真的抓到料。
7. **會直接改動 public 產物並發佈**：流程尾端 `git push` 觸發 GitHub Pages。後台呼叫等於「抓到什麼就發佈什麼」，缺乏審核關卡；建議後台化時把「抓取」與「發佈」拆成兩階段。
8. **互動元素**：bat 的 `pause` 必須移除才能無人值守。
9. **SSL 驗證關閉 / 憑證信任**：5 條來源 `verify_ssl=False`，後台安全審視時需知悉此現況。
10. **併發/鎖**：SQLite 單檔，若後台多工同時跑同一顆 DB 可能鎖衝突；目前設計假設單機單次執行。

---

## 附錄 A：8 張表（`sql/schema.sql`）與一鍵流程的關係

| 表 | 一鍵流程是否寫入 | 說明 |
|---|---|---|
| `cinema_chains` | 否（前置匯入） | 影城品牌、official/crawl/booking URL、`all_locations_assumed_showing` |
| `cinema_locations` | 否（前置匯入 + geocode） | 據點、地址、經緯度、`source_location_code`、`location_url` |
| `movies` | **是**（無則新增） | 追蹤電影 |
| `movie_targets` | 否 | 電影×影城/據點的上映關係（`chain_all_locations` / `single_location`），一鍵流程未使用 |
| `crawl_runs` | **是**（每來源一列） | 爬蟲執行紀錄，判斷成功/失敗的可靠來源 |
| `raw_pages` | 否（改存檔案） | schema 有此表但一鍵爬蟲未寫（原始頁改存 `data/output/showtimes/`） |
| `showtimes` | **是**（先刪後 upsert） | 場次；唯一索引 `ux_showtimes_identity` |
| `kml_exports` | 否 | 供 `export_kml.py`（不在一鍵流程） |

另有兩個 view：`v_location_map_points`（export_geojson 無片名模式用）、`v_showtime_map_points`；以及 5 個 `updated_at` 觸發器。

---

## 附錄 B：與 README / DECISIONS 不一致或值得注意之處（盤點發現）

1. **威秀是「有畫面」瀏覽器**：`fetch_vieshow` 用 `headless=False, slow_mo=200`，README/DECISIONS 只泛稱「用 Playwright」，未點明它需要顯示器；這對後台無頭環境是關鍵限制。
2. **README「第一版已接上：秀泰、國賓、美麗新、親親、王牌映画…新光需再補專門場次 API」與現況不符**：程式其實已接入 18 條 fetcher（含新光 `fetch_skcinemas` 與威秀）。README 第 226 行那句是較舊的敘述，第 290–313 行的「2026-06-26 場次來源狀態」才與程式一致（19 家）。
3. **`raw_pages` 表未被一鍵爬蟲使用**：DECISIONS/README 把「保留原始回應方便查錯」對應到資料庫紀錄，但實際原始頁是存到 `data/output/showtimes/` 檔案，`raw_pages` 在此流程未寫入。
4. **失敗不影響 exit code**：README/DECISIONS 把 bat 描述成線性成功流程，但實務上「部分來源失敗甚至全部抓 0 筆」仍會 commit/push，bat 的 errorlevel 檢查抓不到資料品質問題（見第 9 節）。
5. **硬寫的當期字串**：`fetch_windlion` 內 `"2026-06-26(五)"`、`fetch_umovie` 內 `"Toy Story 5"` 是特定片/日的殘留硬寫，換片換日需注意。
6. **`export_geojson` top-level `features` 只放第一部電影**：多片時前端主要靠 `movie_features` 切換；`features` 僅為第一部，這點文件未特別說明。
7. **KML 與一鍵流程無關**：`更新地圖.bat` 完全不呼叫 `export_kml.py`；KML 是另行手動指令。
8. **repo 內未附 SQLite**：確認 `data/` 下沒有 committed `.sqlite`，一鍵流程依賴本機那顆未進版控的資料庫。
9. **電影清單第 2 行無空白**（`2.名偵探柯南...`）仍能被去編號正則正確解析；標題含冒號會原樣保留為 `movies.title`。
