# movie_map_admin 後台

「台灣電影上映影城地圖」專案的 Django 後台管理系統。

## 這是什麼

這個後台是整個地圖服務的**控制面（control plane）**，提供：

- 登入 / 權限管理（管理員、編輯者兩種角色）
- 編輯影城（cinema）、電影（movie）、上映場次等資料
- 查看爬蟲（scripts/ 下各支 fetch_*.py）寫入的資料與紀錄

後台的 models 是**唯讀對映（unmanaged models，`managed=False`）**現有的
SQLite（`data/movie_map.sqlite`）既有 8 張業務表，Django 完全不會、也不應該
去改動這些表的 schema（欄位、索引、外鍵等都以 `sql/schema.sql` 與各支爬蟲
腳本為準）。Django 自己的 `migrate` 只會新增／維護它自身需要的表
（`auth_*`、`django_*` 等），兩者在同一個 SQLite 檔案裡井水不犯河水。

## 本機啟動步驟

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # 視需要編輯

# 確保專案根已有 data/movie_map.sqlite（用專案根的 python scripts/init_db.py 產生）

python manage.py migrate            # 建 Django 自身表 + tracked_movie 新表，不動現有 8 張 unmanaged 業務表
python manage.py seed_roles         # 建立「管理員」「編輯者」兩個群組與權限
python manage.py import_movie_list  # （選用）把現有《電影清單.txt》匯入追蹤片單開帳
python manage.py createsuperuser
python manage.py runserver
```

啟動後可在 `http://127.0.0.1:8000/dashboard/` 看到營運儀表板；根路徑 `/`
會自動導向 `/dashboard/`；`/admin/` 是原本的資料管理後台；`/healthz/`
提供一個不觸碰資料庫的健康檢查端點，供雲端平台探測服務存活狀態。

### 營運儀表板

啟動後首頁（`/`，實際會導向 `/dashboard/`）是給營運人員看的儀表板，內容
包含：

- 今日各爬蟲來源（`scripts/` 下各支 `fetch_*.py`）的成功／失敗狀態
- 今日總場次數
- 有場次的影城數
- 上次資料更新時間、上次 GeoJSON 更新時間
- 頁面上方提供日期選擇器，可切換檢視其他日期的統計

儀表板右上角提供捷徑，可快速跳到 `/admin/` 做資料管理，或開啟公開地圖
頁面查看實際成果。

儀表板本身以 `staff_member_required` 保護，未登入時會自動導向 `/admin/`
的登入頁，登入後才能看到統計內容（view 實作見 `mapdata/views.py` 的
`dashboard` 函式，模板為 `mapdata/templates/mapdata/dashboard.html`）。

### 追蹤電影管理（Phase 3）

`tracked_movie` 是後台**自己擁有的 managed 新表**（有正式 migration），用來
取代專案根的《電影清單.txt》成為「追蹤電影」的真相來源。它**不影響**現有
8 張 unmanaged 業務表。

首次啟用流程：

1. `python manage.py migrate` 會建立 `tracked_movie` 表。
2. `python manage.py import_movie_list` 把現有《電影清單.txt》匯入開帳
   （可加 `--dry-run` 先預覽）。

日常使用：

- 編輯者在 `/admin/` 的「追蹤電影」新增／停用電影、填別名（一行一個）與
  上映日；每筆會自動記錄 `created_by` / `updated_by` 稽核欄位。
- 要讓現有爬蟲吃到最新清單時，執行 `python manage.py export_movie_list`
  把 `is_active=True` 的追蹤電影寫回《電影清單.txt》（供現有 `scripts/` 爬蟲
  讀取）。覆寫前會自動備份舊檔到 `data/backup/movie_title_YYYYMMDD_HHMMSS.txt`
  （可加 `--dry-run` 先預覽）。這是過渡相容手段；之後 Phase 4/5 會改由後台
  直接觸發更新，不再經過 txt。

### 關於 `python manage.py migrate`

這個指令會在 `data/movie_map.sqlite` 裡新增 Django 內建需要的表
（`auth_user`、`auth_group`、`django_session`、`django_admin_log` 等）**與
`tracked_movie` 這張後台自有的新表**。它**不會**動到現有的 8 張 unmanaged
業務表，因為 `mapdata` app 底下對映那些表的 models 都設定為
`managed = False`；只有 `TrackedMovie` 是 managed，會由 migration 建立與維護。

## 雲端部署備註

部署到雲端（Render / Railway / Fly.io / GCP 等）時，透過環境變數切換設定：

- `DATABASE_URL`：設定後會自動改連 Postgres（透過 `dj-database-url` 解析），
  不設定則沿用本機的 SQLite 預設值。
- `DJANGO_DEBUG=0`：正式環境務必關閉除錯模式。
- `DJANGO_ALLOWED_HOSTS`：填入正式網域，例如 `admin.example.com`。
- `DJANGO_CSRF_TRUSTED_ORIGINS`：填入完整 origin，例如
  `https://admin.example.com`。
- `DJANGO_SECRET_KEY`：務必換成隨機且保密的字串，不可沿用預設值。
- `PUBLIC_MAP_URL`（選填）：公開地圖的網址，供營運儀表板上「查看公開地圖」
  按鈕連結使用；不設定時該按鈕會隱藏或使用預設值（實際行為以
  `mapdata.views.dashboard` 的實作為準）。

部署流程大致如下：

```bash
pip install -r requirements.txt
python manage.py collectstatic --noinput   # 由 WhiteNoise 供應 /admin 的靜態檔
python manage.py migrate
gunicorn movie_map_admin.wsgi:application
```

## 角色與權限

- **管理員（Admin）**：完整權限，可管理使用者帳號、群組權限，以及所有影城
  ／電影資料的新增、修改、刪除。
- **編輯者（Editor）**：僅能新增、修改影城／電影等業務資料，不可管理使用者
  帳號或群組權限，也不可刪除資料（避免誤刪爬蟲寫入的既有資料）。

（實際的群組與權限內容由 `seed_roles` 管理指令建立與維護，此檔案僅說明其
設計用意。）
