# 每日排程更新

排程每天固定時間自動：**從後台讀最新追蹤電影 → 爬場次 → 匯出 GeoJSON → 推 GitHub Pages**。公開地圖靠 GitHub Pages 自動部署。

> **主排程 = GitHub Actions（雲端，見下方第一節）。** 本機工作排程器／`更新地圖.bat` 改為**手動備援**，平常不需要開機掛著跑。兩條路線用的是同一支 `scripts/daily_update.py`、同一份後台片單，可互相替換。

---

## 一、GitHub Actions 每日排程（主要方式）

Workflow：`.github/workflows/daily-crawl.yml`，每天**台灣時間 07:00** 自動執行，並可在 Actions 頁面手動觸發（workflow_dispatch，可指定日期）。

### 這條路線的資料來源與後台關係

| 資料 | 來源 | 與後台關係 |
|------|------|-----------|
| 要爬哪些電影（片單） | 後台 API `GET /api/tracked-movies/` → 寫入《電影清單.txt》 | ✅ 相關（後台 TrackedMovie 是真實來源；斷線退回快取／repo 內《電影清單.txt》） |
| 要爬哪些影城／據點 | repo 內 `data/movie_map.sqlite`（影城主檔） | ❌ 不經後台 |
| 場次 | 即時爬 30+ 家影城官網 | ❌ 與後台無關 |
| 執行結果摘要 | 爬完 POST `/api/crawl-report/` | ✅ 相關（供後台儀表板 KPI） |
| 公開地圖 | 匯出 GeoJSON → 推 main → `pages.yml` 部署 | 與後台無關 |

### 一次性設定（各做一次即可）

1. **把影城主檔 DB 提交進 repo。** GitHub Actions 每次都是全新環境，沒有這顆 DB 就不知道要爬哪些影城／據點代碼（例如威秀需要 `source_location_code`）。`.gitignore` 已放行 `data/movie_map.sqlite`，在本機執行一次爬蟲產生／更新它之後：

   ```bash
   git add data/movie_map.sqlite
   git commit -m "chore: 提交影城主檔 DB 供雲端排程使用"
   git push
   ```

   > 之後若在本機新增／修正影城據點，重新提交這顆 DB 即可讓雲端排程跟著更新。每日爬蟲產生的**場次**不會被提交（workflow 只提交地圖 GeoJSON），主檔保持乾淨。

2. **（要連後台才需要）設定 GitHub Actions Secrets。** repo → **Settings → Secrets and variables → Actions → New repository secret**，新增兩個：

   | Secret 名稱 | 值 |
   |------------|-----|
   | `MUSE_API_BASE_URL` | 後台網址，例如 `https://muse-backend-xxxx.onrender.com` |
   | `MUSE_API_TOKEN` | 與後台 `CRAWLER_API_TOKEN` 相同的字串 |

   > 未設定 Secrets = 純 repo 模式：直接用 repo 內《電影清單.txt》當片單，不拉即時片單也不回報後台（排程仍可正常產出地圖）。

3. **確認排程已生效。** `schedule` 觸發只會從**預設分支（main）**執行——本 workflow 合併進 main 後排程才會開始每天跑。可先到 **Actions → Daily crawl and publish map → Run workflow** 手動跑一次驗證。

### 技術重點

- **時區**：GitHub cron 一律 UTC；台灣 07:00 = 前一天 UTC 23:00，故 `cron: "0 23 * * *"`。尖峰時段實際觸發可能延遲數分鐘。
- **威秀 headful 瀏覽器**：威秀爬蟲需要有畫面的瀏覽器（`headless=False`）。Actions 無頭環境靠 **Xvfb 虛擬顯示器**（`xvfb-run`）解決。
- **容錯**：單一影城爬失敗只記錄該來源錯誤，不中斷整體排程。
- **推送**：workflow 用內建 `GITHUB_TOKEN` 把 GeoJSON 推回 main，觸發 `pages.yml` 自動部署。

---

## 二、本機每日排程（手動備援）

> 本機路線完全免費（不需雲端主機跑爬蟲）。平常交給上面的 GitHub Actions；本機保留給臨時手動補跑或雲端不可用時使用。

## 流程

```
後台 TrackedMovie ──export_movie_list──▶ 電影清單.txt
        │
        ▼  update_map.py（爬 19 家影城 + 匯出 GeoJSON）
  web/data/locations.geojson
        │  git commit / push
        ▼
  GitHub Pages（公開地圖自動更新）
```

單一進入點：`scripts/daily_update.py`。

## 前置需求

1. 已安裝爬蟲相依套件（專案根 `requirements.txt`）與 Playwright 瀏覽器。
2. 已安裝後台相依套件（`backend/requirements.txt`），且本機 `data/movie_map.sqlite` 是後台在用的同一顆（`daily_update.py` 會呼叫後台的 `export_movie_list` 取得最新片單）。
3. **Git 推送憑證已快取**（例如已用 PAT 或 Git Credential Manager 登入過），這樣無人值守時 `git push` 才不會卡在輸入密碼。

> 若未設定雲端 API（下節），`daily_update.py` 會直接用現有《電影清單.txt》，不會讓整個排程失敗。

## 連接雲端後台（API）

要讓本機**自動向雲端 Django 拉最新片單、並把執行摘要回傳**，在本機設定環境變數：

```
MUSE_API_BASE_URL=https://your-render-service.onrender.com
MUSE_API_TOKEN=<與雲端 CRAWLER_API_TOKEN 相同的字串>
MUSE_WORKER_NAME=company-desktop-01   # 選填，預設本機電腦名稱
```

雲端 Render 端也要設一個對應的環境變數 `CRAWLER_API_TOKEN`（同一組隨機字串）。
專案根目錄也可建立 `.env`，格式請參考 `.env.example`；排程執行時會自動載入。

行為：
- **執行前**：`daily_update.py` 向 `/api/tracked-movies/` 拉啟用片單，驗證後**原子寫入** `cache/tracked_movies.json` 與《電影清單.txt》。
- **雲端斷線/逾時**：自動改用上次快取的片單繼續跑，不中斷。
- **執行後**：把本次摘要（唯一 `run_id`、各來源成功/失敗、場次數、git 狀態）POST 到 `/api/crawl-report/`；上傳失敗會留在 `data/output/pending_reports/`，**下次執行自動補送**（以 run_id 冪等，不會重複）。

> 未設定這些變數時 = 純本機模式：只用本機《電影清單.txt》，不連雲端。

## 手動測試

```bash
# 看會執行哪些步驟（不實際跑）
python scripts/daily_update.py --dry-run

# 只重出 GeoJSON、不爬蟲、不推送（快速驗證環境）
python scripts/daily_update.py --no-crawl --no-push

# 正式跑一次（爬蟲 + 推送）
python scripts/daily_update.py
```

常用旗標：`--date YYYY-MM-DD`、`--skip-export`、`--no-crawl`、`--no-push`、`--no-git`。

## Windows 工作排程器設定

1. 開「工作排程器」→ 建立基本工作。
2. 觸發程序：每天，設定你要的時間（例如每天 09:00）。
3. 動作：啟動程式
   - 程式或指令碼：`py`
   - 引數：`-3 scripts\daily_update.py`
   - 開始位置：`C:\你的路徑\muse-site`
4. **重要：勾選「只在使用者登入時執行」**。因為部分影城（如威秀）需要有畫面的瀏覽器（headful），背景服務模式沒有桌面會開不起來。
5. 完成。之後每天到點自動更新並推送。

> 也可以直接排程 `更新地圖.bat`，但它結尾有 `pause` 會等待按鍵，適合手動點擊、不適合無人值守；排程請用上面的 `daily_update.py` 方式。

## Mac / Linux（cron）

```cron
# 每天 09:00 執行（請換成實際路徑與 python）
0 9 * * * cd /path/to/muse-site && /usr/bin/python3 scripts/daily_update.py >> data/output/daily_update.log 2>&1
```

## 疑難排解

- **push 卡住 / 失敗**：多半是憑證沒快取。先手動 `git push` 一次完成登入。
- **威秀等來源抓不到**：確認是「使用者登入時執行」，讓 Playwright 能開有畫面的瀏覽器。
- **想先不推、只在本機看**：加 `--no-push`，再自己開 `web/index.html` 或本機伺服器檢視。
