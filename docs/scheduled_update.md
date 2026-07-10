# 本機每日排程更新（免費路線）

讓本機每天固定時間自動：**從後台讀最新追蹤電影 → 爬場次 → 匯出 GeoJSON → 推 GitHub Pages**。這條路線完全免費（不需要雲端主機跑爬蟲），公開地圖靠 GitHub Pages 自動部署。

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

> 若後台尚未設定，`daily_update.py` 會自動略過匯出步驟、改用現有《電影清單.txt》，不會讓整個排程失敗。

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
