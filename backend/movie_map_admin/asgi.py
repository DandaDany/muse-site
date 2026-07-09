"""
movie_map_admin 專案的 ASGI 進入點。

目前後台以同步 WSGI（gunicorn）為主要部署方式；
本檔案保留給日後若需要非同步伺服器（例如 uvicorn / daphne）時使用。
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "movie_map_admin.settings")

application = get_asgi_application()
