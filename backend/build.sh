#!/usr/bin/env bash
# Render build script（在 backend/ 目錄執行）
# 放在 build 階段的原因：Render 免費方案不支援 preDeployCommand，
# 而 build 階段已可存取 DATABASE_URL，故在此完成資料庫初始化。
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input

# 資料庫初始化（皆為冪等，可重複部署）
python manage.py migrate --no-input          # Django 自身表 + tracked_movie
python manage.py init_business_schema         # 在 Postgres 建 8 張業務表
python manage.py seed_roles                   # 管理員 / 編輯者 群組權限
python manage.py ensure_admin                 # 依環境變數建初始管理員帳號

# 影城代碼（source_location_code）以版控 CSV 為權威來源，每次部署自動同步進 Postgres。
# 冪等且安全：只補代碼與 CSV 有值的欄位，不會清掉後台手動維護的地址/經緯度。
# 讓「全雲端」運作不需經本機——威秀等 headful 來源的代碼靠這條進後台。
python manage.py import_cinema_csv

# 選用：初次開帳時把 web/data/locations.geojson 的影城主檔匯入雲端。
# 設定環境變數 SEED_FROM_GEOJSON=1 → 本次部署會匯入；匯完建議移除該變數，
# 避免每次部署都覆寫（會蓋掉你在後台手動修過的地址/經緯度）。
if [ "$SEED_FROM_GEOJSON" = "1" ]; then
  echo "SEED_FROM_GEOJSON=1 → 匯入影城主檔"
  python manage.py import_from_geojson
fi
