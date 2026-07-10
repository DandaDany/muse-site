"""每日排程更新（Worker）：拉片單 → 爬蟲 → GeoJSON → 推 Pages → 回傳摘要。

資料流（每次執行同步一次；雲端斷線仍可執行）：

    [執行前] 向雲端 Django 拉啟用片單（API）→ 原子寫入 電影清單.txt
             （API 失敗 → 用上次快取；未設定 API → 用現有 txt）
    [執行]   本機爬蟲 → 本機 SQLite → GeoJSON → git push（記錄各階段狀態）
    [執行後] 組執行摘要（唯一 run_id）→ 先落地 pending_reports → POST 回雲端
             （outbox：上傳成功才刪檔；失敗下次重送，以 run_id 冪等不重複）

設定見 scripts/muse_api.py 的環境變數（MUSE_API_BASE_URL / MUSE_API_TOKEN）。
排程方式見 docs/scheduled_update.md。

旗標：--date / --no-crawl / --no-push / --no-git / --skip-pull / --dry-run
"""

from __future__ import annotations

import argparse
import secrets
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import muse_api  # noqa: E402
from update_map import read_movie_titles  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parents[1]
MOVIE_LIST = PROJECT_DIR / "電影清單.txt"
DB_PATH = PROJECT_DIR / "data" / "movie_map.sqlite"


def run(cmd, check=True):
    print("→", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, cwd=str(PROJECT_DIR), check=check)


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)


def max_crawl_run_id() -> int:
    if not DB_PATH.exists():
        return 0
    try:
        con = sqlite3.connect(str(DB_PATH))
        row = con.execute("SELECT COALESCE(MAX(id), 0) FROM crawl_runs").fetchone()
        con.close()
        return row[0] or 0
    except sqlite3.Error:
        return 0


def collect_sources(pre_max_id: int):
    """從本次新增的 crawl_runs（id > pre_max_id）依來源彙總。"""
    sources: dict[str, dict] = {}
    if not DB_PATH.exists():
        return []
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT source_name, status, rows_found, rows_saved, error_message "
        "FROM crawl_runs WHERE id > ?",
        (pre_max_id,),
    ).fetchall()
    con.close()
    for r in rows:
        name = r["source_name"] or "(未命名來源)"
        s = sources.setdefault(
            name, {"name": name, "found": 0, "saved": 0, "statuses": [], "error_message": None}
        )
        s["found"] += r["rows_found"] or 0
        s["saved"] += r["rows_saved"] or 0
        s["statuses"].append(r["status"])
        if r["error_message"] and not s["error_message"]:
            s["error_message"] = r["error_message"]
    result = []
    for s in sources.values():
        statuses = s.pop("statuses")
        if all(x == "success" for x in statuses):
            status = "success"
        elif all(x == "failed" for x in statuses):
            status = "failed"
        else:
            status = "partial"
        s["status"] = status
        result.append(s)
    return result


def build_summary(sources):
    return {
        "sources_total": len(sources),
        "sources_success": sum(1 for s in sources if s["status"] == "success"),
        "sources_failed": sum(1 for s in sources if s["status"] in ("failed", "partial")),
        "showtimes_found": sum(s["found"] for s in sources),
        "showtimes_saved": sum(s["saved"] for s in sources),
    }


def overall_status(summary, crawled: bool) -> str:
    if not crawled:
        return "skipped"
    total = summary["sources_total"]
    if total == 0:
        return "failed"
    if summary["sources_failed"] == 0:
        return "success"
    if summary["sources_success"] == 0:
        return "failed"
    return "partial_success"


def git_publish(no_push: bool):
    """回傳 (push_status, commit_sha)。push_status ∈ success/failed/no_change/skipped。"""
    run(["git", "add", "."])
    unchanged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=str(PROJECT_DIR)
    ).returncode == 0
    if unchanged:
        return "no_change", _commit_sha()
    if subprocess.run(["git", "commit", "-m", "Update map data (scheduled)"], cwd=str(PROJECT_DIR)).returncode != 0:
        return "failed", _commit_sha()
    if no_push:
        return "skipped", _commit_sha()
    ok = subprocess.run(["git", "push"], cwd=str(PROJECT_DIR)).returncode == 0
    return ("success" if ok else "failed"), _commit_sha()


def _commit_sha():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(PROJECT_DIR),
            capture_output=True, text=True,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="每日排程：拉片單 → 爬蟲 → GeoJSON → 推送 → 回傳摘要。")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--no-crawl", action="store_true", help="不爬蟲，只重出 GeoJSON。")
    parser.add_argument("--no-push", action="store_true", help="commit 但不 push。")
    parser.add_argument("--no-git", action="store_true", help="完全不做 git 操作。")
    parser.add_argument("--skip-pull", action="store_true", help="不向雲端拉片單，用現有 電影清單.txt。")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_id = new_run_id()
    started_at = muse_api.now_iso()
    print("=" * 50)
    print(f"每日地圖更新  run_id={run_id}")
    print(f"Date: {args.date}")
    print("=" * 50)

    if args.dry_run:
        print("[dry-run] 拉片單(API) → " + ("重出 GeoJSON" if args.no_crawl else "爬蟲+GeoJSON")
              + (" → git" if not args.no_git else "") + " → 回傳摘要")
        return

    # 1) 拉片單（API → 快取 → txt）
    movie_list_meta = {"source": "skipped"}
    if not args.skip_pull:
        movies, movie_list_meta = muse_api.pull_movie_list()
        if movies is not None:
            muse_api.write_movie_list_txt(movies)
        print(f"[片單] 來源={movie_list_meta.get('source')} "
              f"版本={movie_list_meta.get('version')} 數量={movie_list_meta.get('count')}"
              + (f" 錯誤={movie_list_meta['api_error']}" if movie_list_meta.get("api_error") else ""))

    # 2) 爬蟲 + GeoJSON
    pre_max = max_crawl_run_id()
    crawled = not args.no_crawl
    if crawled:
        run([sys.executable, "scripts/update_map.py", "--date", args.date])
    else:
        titles = read_movie_titles(MOVIE_LIST)
        export_args = ["scripts/export_geojson.py", "--date", args.date]
        for t in titles:
            export_args.extend(["--movie-title", t])
        run([sys.executable, *export_args])

    sources = collect_sources(pre_max)
    summary = build_summary(sources)

    # 3) 發佈
    git = {"push_status": "skipped", "commit_sha": None}
    if not args.no_git:
        push_status, sha = git_publish(args.no_push)
        git = {"push_status": push_status, "commit_sha": sha}

    # 4) 組報告 → 先落地 → 上傳（含補送先前失敗的）
    report = {
        "run_id": run_id,
        "worker_name": muse_api.worker_name(),
        "started_at": started_at,
        "finished_at": muse_api.now_iso(),
        "show_date": args.date,
        "status": overall_status(summary, crawled),
        "movie_list": movie_list_meta,
        "summary": summary,
        "sources": sources,
        "git": git,
    }
    muse_api.save_pending_report(report)
    sent, failed = muse_api.flush_pending_reports()
    print(f"[摘要] 狀態={report['status']} 來源成功/失敗={summary['sources_success']}/{summary['sources_failed']} "
          f"場次={summary['showtimes_saved']} git={git['push_status']}")
    print(f"[回傳] 已上傳 {sent} 份、待送 {failed} 份")
    print("[DONE] 完成。")


if __name__ == "__main__":
    main()
