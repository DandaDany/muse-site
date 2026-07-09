"""
movie_map_admin 專案的 WSGI 進入點。

雲端部署（例如 gunicorn）會透過本模組取得 WSGI callable：
    gunicorn movie_map_admin.wsgi:application
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "movie_map_admin.settings")

application = get_wsgi_application()
