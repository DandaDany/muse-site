#!/usr/bin/env bash
# Render build script（在 backend/ 目錄執行）
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
