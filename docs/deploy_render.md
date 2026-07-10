# 後台上線指南（Render）

把 muse-site 後台（控制面）部署到 Render，取得一個可線上登入的網址。

## 前置

- 一個 GitHub 帳號（能存取 `DandaDany/muse-site`）。
- 部署設定檔 `render.yaml` 已在分支 `claude/theater-backend-system-y7wdl0`。

## 步驟

1. 到 <https://render.com>，用 **GitHub 登入**。
2. 右上 **New → Blueprint**。
3. 選擇 repo `DandaDany/muse-site`。
4. **分支選 `claude/theater-backend-system-y7wdl0`**（`render.yaml` 在這個分支；若已合併到 main 則選 main）。
5. Render 會讀 `render.yaml`，顯示將建立：
   - Web 服務 `muse-backend`（Django + gunicorn）
   - Postgres 資料庫 `muse-backend-db`
6. 在 Web 服務的 **Environment** 填入三個機密環境變數（`render.yaml` 標為 `sync:false`，不會寫進 repo）：
   - `DJANGO_SUPERUSER_USERNAME`：你要的管理員帳號，例如 `admin`
   - `DJANGO_SUPERUSER_PASSWORD`：一組強密碼
   - `DJANGO_SUPERUSER_EMAIL`：你的信箱（選填）
7. 按 **Apply**，等 build 完成（首次約 3~5 分鐘）。
8. 開 `https://muse-backend.onrender.com/`（實際網址以 Render 顯示為準）：
   - `/` → 營運儀表板
   - `/admin/` → 用步驟 6 的帳密登入

## build 會自動做什麼

`backend/build.sh` 依序執行：`pip install` → `collectstatic` → `migrate`（建 Django 自身表 + `tracked_movie`）→ `init_business_schema`（在 Postgres 建 8 張業務表）→ `seed_roles`（建管理員/編輯者群組）→ `ensure_admin`（建初始管理員）。全部冪等，可重複部署。

## 把本機影城資料灌進雲端（可選，但建議）

上線後雲端 Postgres 是空的。用 `import_from_sqlite` 指令把本機
`data/movie_map.sqlite` 的人工資料（品牌／據點／電影／追蹤目標）推上雲端：

1. 到 Render 的 Postgres 頁面複製 **External Database URL**（外部連線字串）。
2. 在本機專案 `backend/` 底下執行（先 `--dry-run` 預覽）：

   ```bash
   # Windows PowerShell
   $env:DATABASE_URL="postgres://...(External URL)..."
   python manage.py import_from_sqlite ../data/movie_map.sqlite --dry-run
   python manage.py import_from_sqlite ../data/movie_map.sqlite

   # Mac/Linux
   DATABASE_URL="postgres://...(External URL)..." python manage.py import_from_sqlite ../data/movie_map.sqlite
   ```

3. 指令冪等，可重複執行；預設不含場次（場次由爬蟲產生），需要時加
   `--with-showtimes`。地址／經緯度等人工欄位會完整保留。

## 上線初期須知

- **影城/場次資料一開始是空的**：用上面的 `import_from_sqlite` 灌入即可；也可先在
  `/admin/` 的「追蹤電影」直接新增。完整的雙向自動同步屬 Phase 6。
- **免費方案會休眠**：閒置一段時間後首次連線會慢約 30~50 秒喚醒；每月有時數上限。
- **免費 Postgres 約 30 天到期**：正式使用請升級付費方案（約 $7/月）。

## 更新部署

之後 push 到所選分支，Render 會自動重新 build 部署。
