# GA4 設定指南（地圖流量分析 + 儀表板顯示）

分兩段：**A. 讓地圖開始收集流量**（必做、最簡單）、**B. 讓儀表板顯示數字**（選做、需 GCP 服務帳號）。

---

## A. 地圖收集流量（GA4 追蹤碼）

1. 到 <https://analytics.google.com> → 建立「GA4 資源（Property）」。
2. 建立一個「網頁」資料串流，網址填你的公開地圖（GitHub Pages 網址）。
3. 取得「評估 ID」，格式 `G-XXXXXXXXXX`。
4. 編輯 `web/index.html`，把 **兩處** `G-XXXXXXXXXX` 換成你的評估 ID：
   - `<script async src="...gtag/js?id=G-XXXXXXXXXX">`
   - `window.GA4_MEASUREMENT_ID = 'G-XXXXXXXXXX';`
5. commit + push（GitHub Pages 會自動部署）。

完成後，GA4 即時報表就能看到訪客。地圖已內建三個事件：
- `page_view`（自動）
- `select_movie`（使用者切換電影，參數 `movie_title`）
- `select_cinema`（點擊影城 pin，參數 `cinema` / `chain` / `city` / `movie_title`）

> 評估 ID 是公開資訊，放在前端原始碼是正常且必要的，不是機密。

---

## B. 儀表板顯示流量（GA4 Data API）

讓 Django 儀表板的「網站流量」區顯示近 7 日活躍使用者、瀏覽次數、事件次數。
未設定時該區會顯示「尚未連接」，不影響其他功能。

1. 到 <https://console.cloud.google.com> 建立（或選一個）GCP 專案。
2. 啟用 **Google Analytics Data API**。
3. 建立一個**服務帳號（Service Account）**，產生 **JSON 金鑰**並下載。
4. 到 GA4 → 管理 → 資源存取管理，把服務帳號的 email 加為「檢視者（Viewer）」。
5. 取得 GA4 的**資源 ID**（純數字，在 GA4「管理 → 資源設定」可看到，例如 `123456789`）。
6. 在 Render 的 `muse-backend` 服務 → Environment 設定：
   - `GA4_PROPERTY_ID` = 你的資源 ID（純數字）
   - `GA4_CREDENTIALS_JSON` = 服務帳號 JSON 金鑰的**整段內容**（直接貼進去）
   - `GA4_PROPERTY_URL`（選填）= GA4 報表網址，儀表板「開啟 GA4」按鈕用
7. 存檔 → Render 重新部署 → 儀表板「網站流量（GA4）」就會顯示數字。

後端相依 `google-analytics-data` 已在 `backend/requirements.txt`，Render build 會自動安裝。

### 疑難排解
- 顯示「GA4 連線失敗」：多半是①服務帳號沒被加到 GA4 檢視者、②資源 ID 填錯、③JSON 貼不完整。
- 剛裝好可能沒資料：GA4 需要一點時間累積；即時報表可先驗證追蹤碼有效。
- 資料有 10 分鐘快取（避免打爆 API 配額），數字不會秒級即時。
