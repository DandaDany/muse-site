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

python manage.py migrate            # 只建 Django 自身的 auth/session/admin 表，不動現有 8 張表
python manage.py seed_roles         # 建立「管理員」「編輯者」兩個群組與權限
python manage.py createsuperuser
python manage.py runserver
```

啟動後可在 `http://127.0.0.1:8000/admin/` 登入後台；根路徑 `/` 會自動導向
`/admin/`；`/healthz/` 提供一個不觸碰資料庫的健康檢查端點，供雲端平台探測
服務存活狀態。

### 關於 `python manage.py migrate`

這個指令**只會**在 `data/movie_map.sqlite` 裡新增 Django 內建需要的表
（`auth_user`、`auth_group`、`django_session`、`django_admin_log` 等），
**不會**動到現有的 8 張業務表，因為 `mapdata` app 底下對映這些表的 models
都設定為 `managed = False`（該行為由負責 models.py 的人維護，本後台骨架不
包含 models 本身）。也因為如此，`mapdata` 底下故意只保留一個空的
`migrations/__init__.py`，不會、也不應該產生任何 migration 檔。

## 雲端部署備註

部署到雲端（Render / Railway / Fly.io / GCP 等）時，透過環境變數切換設定：

- `DATABASE_URL`：設定後會自動改連 Postgres（透過 `dj-database-url` 解析），
  不設定則沿用本機的 SQLite 預設值。
- `DJANGO_DEBUG=0`：正式環境務必關閉除錯模式。
- `DJANGO_ALLOWED_HOSTS`：填入正式網域，例如 `admin.example.com`。
- `DJANGO_CSRF_TRUSTED_ORIGINS`：填入完整 origin，例如
  `https://admin.example.com`。
- `DJANGO_SECRET_KEY`：務必換成隨機且保密的字串，不可沿用預設值。

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
