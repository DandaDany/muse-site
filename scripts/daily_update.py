"""每日排程更新：後台追蹤電影 → 爬蟲 → GeoJSON → 推送 GitHub Pages。

這是「本機排程」路線的單一進入點（免雲端主機、完全免費）：

    後台（TrackedMovie）
        │  export_movie_list（Django 指令）
        ▼
    電影清單.txt
        │  update_map.py（爬 19 家影城場次 + 匯出 GeoJSON）
        ▼
    web/data/locations.geojson
        │  git commit / push
        ▼
    GitHub Pages（公開地圖自動更新）

用 Windows 工作排程器（或 cron）每天固定時間跑這支即可。詳見
docs/scheduled_update.md。

常用旗標：
    --date YYYY-MM-DD   指定日期（預設今天）
    --skip-export       不從後台匯出，直接用現有 電影清單.txt
    --no-crawl          不爬蟲，只用現有場次資料重出 GeoJSON（測試/重建用）
    --no-push           commit 但不 push
    --no-git            完全不做 git 操作
    --dry-run           只印出將執行的步驟
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_DIR / "backend"
MOVIE_LIST = PROJECT_DIR / "電影清單.txt"

# 重用 update_map.py 的清單解析（去編號、去註解、去重）。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_map import read_movie_titles  # noqa: E402


def run(cmd, cwd=PROJECT_DIR, env=None, check=True):
    print("→", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, cwd=str(cwd), env=env, check=check)


def export_tracked_movies() -> None:
    """從後台 TrackedMovie 匯出《電影清單.txt》（best-effort）。

    後台若尚未安裝／無法啟動，不讓整個排程失敗，改用現有 txt 繼續。
    """
    env = dict(os.environ, DJANGO_SETTINGS_MODULE="movie_map_admin.settings")
    try:
        run([sys.executable, "manage.py", "export_movie_list"], cwd=BACKEND_DIR, env=env)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"[warn] 無法從後台匯出追蹤電影（{exc}）；改用現有《電影清單.txt》。")


def crawl_and_export(show_date: str) -> None:
    run([sys.executable, "scripts/update_map.py", "--date", show_date])


def export_only(show_date: str) -> None:
    """不爬蟲，只用資料庫既有場次重新輸出 GeoJSON。"""
    titles = read_movie_titles(MOVIE_LIST)
    args = ["scripts/export_geojson.py", "--date", show_date]
    for title in titles:
        args.extend(["--movie-title", title])
    run([sys.executable, *args])


def git_publish(no_push: bool) -> None:
    run(["git", "add", "."])
    # 沒有變更就不 commit（避免空 commit）。
    unchanged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=str(PROJECT_DIR)
    ).returncode == 0
    if unchanged:
        print("[info] 沒有變更，略過 commit/push。")
        return
    run(["git", "commit", "-m", "Update map data (scheduled)"])
    if no_push:
        print("[info] --no-push：略過 push。")
        return
    run(["git", "push"])


def main() -> None:
    parser = argparse.ArgumentParser(description="每日排程：後台追蹤電影 → 爬蟲 → GeoJSON → 推送。")
    parser.add_argument("--date", default=date.today().isoformat(), help="日期，預設今天。")
    parser.add_argument("--skip-export", action="store_true", help="不從後台匯出，直接用現有 txt。")
    parser.add_argument("--no-crawl", action="store_true", help="不爬蟲，只重出 GeoJSON。")
    parser.add_argument("--no-push", action="store_true", help="commit 但不 push。")
    parser.add_argument("--no-git", action="store_true", help="完全不做 git 操作。")
    parser.add_argument("--dry-run", action="store_true", help="只印出將執行的步驟。")
    args = parser.parse_args()

    print("=" * 50)
    print("每日地圖更新")
    print(f"Date: {args.date}")
    print("=" * 50)

    if args.dry_run:
        steps = []
        if not args.skip_export:
            steps.append("export_movie_list（後台→txt）")
        steps.append("export_geojson（--no-crawl）" if args.no_crawl else "update_map（爬蟲+GeoJSON）")
        if not args.no_git:
            steps.append("git commit" + ("" if args.no_push else " + push"))
        print("[dry-run] 將依序執行：" + " → ".join(steps))
        return

    if not args.skip_export:
        export_tracked_movies()

    if args.no_crawl:
        export_only(args.date)
    else:
        crawl_and_export(args.date)

    if not args.no_git:
        git_publish(args.no_push)

    print("[DONE] 完成。")


if __name__ == "__main__":
    main()
