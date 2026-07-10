# 上線檢查清單 / 完成度

## 已完成的功能

| 區塊 | 內容 | 狀態 |
|---|---|---|
| 後台骨架 | Django 登入、管理員/編輯者兩角色、8 表唯讀對映 | ✅ |
| 儀表板 | 今日各來源成功/失敗、場次/影城/電影 KPI、資料品質提醒 | ✅ |
| 追蹤電影 | DB 表管理片單、別名、啟用；txt 雙向相容 | ✅ |
| 每日排程 | daily_update：拉片單→爬蟲→GeoJSON→推 Pages→回傳摘要 | ✅ |
| 雲端橋接 API | GET tracked-movies / POST crawl-report（token、run_id 冪等、outbox 容錯） | ✅ |
| 儀表板讀報告 | 雲端顯示本機回傳的真實數字（無報告則退回本機） | ✅ |
| 雲端部署 | Render Blueprint + Postgres；SQLite→雲端匯入指令 | ✅ |
| 網站流量 | 地圖 GA4 追蹤 + 儀表板流量區 | ✅（需填 ID/憑證啟用） |

## 上線前要設定的東西

### Render（雲端後台）
- [ ] `CRAWLER_API_TOKEN` = 一組長隨機字串（本機 API 驗證用）
- [ ] `DJANGO_SUPERUSER_USERNAME` / `PASSWORD` / `EMAIL`（初始管理員）
- [ ] （選）`GA4_PROPERTY_ID` + `GA4_CREDENTIALS_JSON` + `GA4_PROPERTY_URL`（儀表板顯示流量，見 `docs/ga4_setup.md`）
- [ ] （選）`PUBLIC_MAP_URL`（公開地圖網址）

### 本機（排程機器）
- [ ] `MUSE_API_BASE_URL` = Render 網址
- [ ] `MUSE_API_TOKEN` = 與 `CRAWLER_API_TOKEN` 相同
- [ ] （選）`MUSE_WORKER_NAME` = 電腦名稱
- [ ] 安裝 `requirements.txt`（爬蟲）與 Playwright 瀏覽器
- [ ] `git push` 憑證已快取（無人值守時才能推送）
- [ ] 設定工作排程器每天執行 `scripts/daily_update.py`（見 `docs/scheduled_update.md`）

### 地圖（GitHub Pages）
- [ ] `web/index.html` 兩處 `G-XXXXXXXXXX` 換成 GA4 評估 ID（見 `docs/ga4_setup.md`）
- [ ] 首次把本機影城資料匯入雲端：`import_from_sqlite`（見 `docs/deploy_render.md`）

## 驗證流程（設定完成後跑一次）
1. 後台 `/admin/` 能登入、能新增「追蹤電影」。
2. 本機 `python scripts/daily_update.py` 跑完：拉到片單、爬蟲、推 Pages、回傳摘要成功。
3. 儀表板顯示「本機回報」的真實數字（場次、來源成功/失敗）。
4. 公開地圖有更新；GA4 即時報表看得到訪客。

## 相關文件
- `docs/backend_architecture.md`：整體架構
- `docs/backend_progress.md`：開發進度與資料流同步原則
- `docs/deploy_render.md`：Render 部署 + 資料匯入
- `docs/scheduled_update.md`：本機排程
- `docs/ga4_setup.md`：GA4 設定
