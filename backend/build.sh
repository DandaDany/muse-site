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
