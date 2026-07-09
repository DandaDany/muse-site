#!/usr/bin/env python
"""Django 的命令列管理工具（manage.py）。"""
import os
import sys


def main() -> None:
    """執行管理任務的進入點。"""
    # 預設使用本專案的 settings 模組；可用環境變數覆寫（例如測試環境）
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "movie_map_admin.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "無法匯入 Django，請確認已安裝並啟用虛擬環境，"
            "且 PYTHONPATH 設定正確（可執行 pip install -r requirements.txt）。"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
