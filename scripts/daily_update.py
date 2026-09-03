"""每日排程更新（Worker）：片單 → 爬蟲 → GeoJSON → 發佈 → 摘要。

遷移期間採雙模式：
- data/control/tracked_movies.json + cinema_master.json 都存在時，GitHub 是 control plane；
- 尚未完成 migration materialization 前，沿用 legacy Django API。
- 兩份 canonical files 只存在其中一份時直接失敗，避免半遷移狀態。

GitHub control mode 不再把 crawl report POST 回 Render；CI 以 Actions log / summary
作為執行紀錄。legacy mode 保留原本 outbox 回報，直到正式切換完成。
"""

from __future__ import annotations

import argparse
import os
import secrets
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import control_data  # noqa: E402
import muse_api  # noqa: E402
from showtime_availability import MAX_SOURCE_LOOKAHEAD_DAYS  # noqa: E402
from update_map import read_movie_titles, write_empty_movie_map  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parents[1]
MOVIE_LIST = PROJECT_DIR / "電影清單.txt"
DB_PATH = PROJECT_DIR / "data" / "movie_map.sqlite"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def run(cmd, check=True):
    print("→", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, cwd=str(PROJECT_DIR), check=check)


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)


def git_control_enabled() -> bool:
    tracked = control_data.TRACKED_MOVIES_PATH.exists()
    cinemas = control_data.CINEMA_MASTER_PATH.exists()
    if tracked != cinemas:
        raise RuntimeError(
            "GitHub control plane is incomplete: tracked_movies.json and cinema_master.json "
            "must appear together"
        )
    return tracked and cinemas


def load_runtime_movie_list() -> dict:
    """Materialize 電影清單.txt + alias cache from GitHub canonical data or legacy API."""
    if git_control_enabled():
        canonical = control_data.load_tracked_movies()
        runtime = control_data.write_runtime_movie_files(
            canonical,
            datetime.now(TAIPEI_TZ).date(),
            MOVIE_LIST,
            muse_api.CACHE_JSON,
        )
        return {
            "source": "git",
            "version": runtime.get("version"),
            "count": runtime.get("count"),
            "cache_age_seconds": 0,
        }

    movies, meta = muse_api.pull_movie_list()
    if movies is not None:
        muse_api.write_movie_list_txt(movies)
    return meta


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


def collect_sources(pre_max_id: int, primary_show_date: str):
    """只彙總本次 primary date 的 crawl runs，未來日期另留在 log。"""
    sources: dict[str, dict] = {}
    if not DB_PATH.exists():
        return []
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT source_name, status, rows_found, rows_saved, error_message "
        "FROM crawl_runs WHERE id > ? AND show_date = ?",
        (pre_max_id, primary_show_date),
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


def existing_export_dates(primary_show_date: str) -> list[str]:
    """找出 P0 連續窗口內 SQLite 真正存在場次的日期，供 --no-crawl 重出。"""
    if not DB_PATH.exists():
        return [primary_show_date]
    start = date.fromisoformat(primary_show_date)
    end = start + timedelta(days=MAX_SOURCE_LOOKAHEAD_DAYS)
    try:
        con = sqlite3.connect(str(DB_PATH))
        rows = con.execute(
            "SELECT DISTINCT show_date FROM showtimes "
            "WHERE show_date BETWEEN ? AND ? ORDER BY show_date",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        con.close()
    except sqlite3.Error:
        return [primary_show_date]
    observed = [row[0] for row in rows if row[0]]
    return list(dict.fromkeys([primary_show_date, *observed]))


def build_no_crawl_export_args(titles: list[str], primary_show_date: str) -> list[str]:
    export_args = ["scripts/export_geojson.py", "--date", primary_show_date]
    for show_date in existing_export_dates(primary_show_date):
        if show_date != primary_show_date:
            export_args.extend(["--additional-date", show_date])
    for title in titles:
        export_args.extend(["--movie-title", title])
    return export_args


def showtime_coverage(show_date: str):
    if not DB_PATH.exists():
        return 0, 0
    try:
        con = sqlite3.connect(str(DB_PATH))
        row = con.execute(
            "SELECT COUNT(DISTINCT location_id), COUNT(DISTINCT movie_id) "
            "FROM showtimes WHERE show_date = ?",
            (show_date,),
        ).fetchone()
        con.close()
        return row[0] or 0, row[1] or 0
    except sqlite3.Error:
        return 0, 0


def build_summary(sources, show_date):
    cinemas, movies = showtime_coverage(show_date)
    return {
        "sources_total": len(sources),
        "sources_success": sum(1 for s in sources if s["status"] == "success"),
        "sources_failed": sum(1 for s in sources if s["status"] in ("failed", "partial")),
        "showtimes_found": sum(s["found"] for s in sources),
        "showtimes_saved": sum(s["saved"] for s in sources),
        "cinemas_with_showtimes": cinemas,
        "movies_with_showtimes": movies,
    }


def overall_status(summary, crawled: bool, movie_count: int | None = None) -> str:
    if movie_count == 0:
        return "success"
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


def write_actions_summary(report: dict) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    summary = report["summary"]
    movies = report["movie_list"]
    lines = [
        "## Daily crawl",
        "",
        f"- Status: **{report['status']}**",
        f"- Show date: `{report['show_date']}`",
        f"- Movie source: `{movies.get('source')}` / count `{movies.get('count')}`",
        f"- Sources success / failed: `{summary['sources_success']} / {summary['sources_failed']}`",
        f"- Showtimes saved: `{summary['showtimes_saved']}`",
    ]
    failed = [s for s in report["sources"] if s["status"] != "success"]
    if failed:
        lines.extend(["", "### Failed / partial sources"])
        lines.extend(f"- {s['name']}: {s['status']} — {s.get('error_message') or 'no error text'}" for s in failed)
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="每日排程：片單 → 爬蟲 → GeoJSON → 發佈 → 摘要。")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--no-crawl", action="store_true", help="不爬蟲，只重出 GeoJSON。")
    parser.add_argument("--no-push", action="store_true", help="commit 但不 push。")
    parser.add_argument("--no-git", action="store_true", help="完全不做 git 操作。")
    parser.add_argument("--skip-pull", action="store_true", help="不更新片單，用現有 電影清單.txt。")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_id = new_run_id()
    started_at = muse_api.now_iso()
    print("=" * 50)
    print(f"每日地圖更新  run_id={run_id}")
    print(f"Date: {args.date}")
    print("=" * 50)

    if args.dry_run:
        mode = "git" if git_control_enabled() else "legacy-backend"
        print(
            f"[dry-run] control={mode} → "
            + ("重出 GeoJSON" if args.no_crawl else "爬蟲+GeoJSON")
            + (" → git" if not args.no_git else "")
        )
        return

    movie_list_meta = {"source": "skipped"}
    if not args.skip_pull:
        movie_list_meta = load_runtime_movie_list()
        print(
            f"[片單] 來源={movie_list_meta.get('source')} "
            f"版本={movie_list_meta.get('version')} 數量={movie_list_meta.get('count')}"
            + (f" 錯誤={movie_list_meta['api_error']}" if movie_list_meta.get("api_error") else "")
        )

    titles = read_movie_titles(MOVIE_LIST)
    movie_count = len(titles)

    pre_max = max_crawl_run_id()
    crawled = not args.no_crawl
    if crawled:
        run([sys.executable, "scripts/update_map.py", "--date", args.date])
    elif titles:
        export_args = build_no_crawl_export_args(titles, args.date)
        run([sys.executable, *export_args])
    else:
        write_empty_movie_map(args.date)

    sources = collect_sources(pre_max, args.date)
    summary = build_summary(sources, args.date)
    if movie_count == 0:
        summary.update({
            "sources_total": 0,
            "sources_success": 0,
            "sources_failed": 0,
            "showtimes_found": 0,
            "showtimes_saved": 0,
            "cinemas_with_showtimes": 0,
            "movies_with_showtimes": 0,
        })

    git = {"push_status": "skipped", "commit_sha": None}
    if not args.no_git:
        push_status, sha = git_publish(args.no_push)
        git = {"push_status": push_status, "commit_sha": sha}

    report = {
        "run_id": run_id,
        "worker_name": muse_api.worker_name(),
        "started_at": started_at,
        "finished_at": muse_api.now_iso(),
        "show_date": args.date,
        "status": overall_status(summary, crawled, movie_count),
        "movie_list": movie_list_meta,
        "summary": summary,
        "sources": sources,
        "git": git,
    }
    write_actions_summary(report)

    if git_control_enabled():
        sent = failed = 0
        print("[回傳] GitHub control mode：不再依賴 Render crawl-report API。")
    else:
        muse_api.save_pending_report(report)
        sent, failed = muse_api.flush_pending_reports()
        print(f"[回傳] 已上傳 {sent} 份、待送 {failed} 份")

    print(
        f"[摘要] 狀態={report['status']} 來源成功/失敗="
        f"{summary['sources_success']}/{summary['sources_failed']} "
        f"場次={summary['showtimes_saved']} git={git['push_status']}"
    )
    print("[DONE] 完成。")


if __name__ == "__main__":
    main()
