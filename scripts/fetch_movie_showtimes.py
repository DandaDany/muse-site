from __future__ import annotations

import argparse
import ast
import html
import json
import os
import re
import ssl
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from init_db import DEFAULT_DB_PATH, init_db


# Windows 排程／主控台可能仍採 CP950；來源名稱含非 CP950 字元時不可中斷整次更新。
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_DIR / "data" / "output" / "showtimes"
TAIPEI = ZoneInfo("Asia/Taipei")
SHOWTIMES_BOOTSTRAP_URL = "https://capi.showtimes.com.tw/4/app/bootstrap"
VIESHOW_URL = "https://www.vscinemas.com.tw/ShowTimes/"
SKCINEMAS_FILMS_URL = "https://www.skcinemas.com/films"
SKCINEMAS_SESSION_API = "https://www.skcinemas.com/api/VistaDataV2/GetSessionByCinemasIDForApp"
SKCINEMAS_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
IN89_API_PATH = "/api/api_movie.php?method=getStagesByDate"
CENTURYASIA_URL = "https://ticket.centuryasia.com.tw/"
MIRANEW_TIMETABLE_URL = "https://www.miranewcinemas.com/Booking/Timetable"
CCMOVIE_URL = "https://www.ccmovie.com.tw/product.php?_path=product_showtimes"
ACE_URL = "https://www.acecinema.com.tw/movie/now"
TMOVIES_URL = "https://www.t-movies.com.tw/index.php"
VENICE_URL = "https://www.venice-cinemas.com.tw/showtime.php?movie_date=&page={page}"
BROADWAY_API = "https://www.broadway-cineplex.com.tw/Movie/GetMovieList/{code}"
UCH_URL = "https://www.uch-movies.tw/time.aspx"
UMOVIE_URL = "https://www.u-movie.com.tw/cinema/page.php?page_type=now&ver=tw&portal=cinema"
LUNA_URL = "https://www.lunacinemax.com.tw/time_schedule.aspx"
ILANMOVIE_URL = "https://ilanmovie.com/index.php"
WINDLION_URL = "https://cinemax.windlion.com.tw/movies.php"
PTCINEMA_URL = "https://ptcinema.movie.com.tw/time?date={show_date}"
HALAR_URL = "https://halarcity.com.tw/browsing/Cinemas/Details/0000000001"
MIRAMAR_URL = "https://www.miramarcinemas.tw/timetable"
NANTAI_URL = "https://www.nt-movie.com.tw/showtime.php"
LUX_URL = "https://www.luxcinema.com.tw/web/2020.php?type=ShowTimes"
MLD_URL = "https://mldcinema.com.tw/TimeList.php"
MACHI_URL = "https://fmmfilmmate.tixi.com.tw/"
SPOT_HS_URL = "https://spot-hs.tixi.com.tw/"
BREEZE_URL = "https://breezecinemas.tixi.com.tw/"
GOVERNOR_URL = "https://governor.tixi.com.tw/"
ESLITE_URL = "https://meet.eslite.com/tw/tc/gallery/movieschedule/201803020001"
NANTOU_URL = "https://www.nantoutheater.com/movie_order?search_date={show_date}&search_time=0"
SHANMING_URL = "https://www.shanmingcinema.com.tw/showtimes.php"
TIMES_URL = "https://www.timescinema.com.tw/times.php"


@dataclass(frozen=True)
class ShowtimeRecord:
    location_id: int
    show_date: str
    start_time: str
    auditorium: str | None
    format: str | None
    language: str | None
    booking_url: str | None
    source_url: str
    raw_text: str


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    table = str.maketrans("０１２３４５６７８９", "0123456789")
    value = html.unescape(value).translate(table).lower()
    return re.sub(r"[\s　:：,，.。、/／()（）\[\]【】\-–—_．・‧|｜'\"“”‘’!！?？~～]+", "", value)


def movie_matches(text: str, aliases: list[str]) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(alias) in normalized for alias in aliases)


def infer_language(format_text: str | None) -> str | None:
    if not format_text:
        return None
    if any(token in format_text for token in ["國語", "中文", "中文版", "中)"]):
        return "國語"
    if any(token in format_text for token in ["英語", "英文", "英文版", "英)"]):
        return "英語"
    if any(token in format_text for token in ["日語", "日文"]):
        return "日語"
    if "韓語" in format_text or "韓文" in format_text:
        return "韓語"
    return None


def request_bytes(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    verify_ssl: bool = True,
) -> bytes:
    base_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }
    if headers:
        base_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=base_headers, method=method)
    context = None if verify_ssl else ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=45, context=context) as response:
        return response.read()


def request_text(url: str, *, headers: dict[str, str] | None = None, verify_ssl: bool = True) -> str:
    raw = request_bytes(url, headers=headers, verify_ssl=verify_ssl)
    return raw.decode("utf-8", errors="replace")


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    verify_ssl: bool = True,
) -> object:
    body = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    merged_headers = {"Accept": "application/json,text/plain,*/*"}
    if payload is not None:
        merged_headers["Content-Type"] = "application/json"
    if headers:
        merged_headers.update(headers)
    raw = request_bytes(url, method=method, data=body, headers=merged_headers, verify_ssl=verify_ssl)
    return json.loads(raw.decode("utf-8", errors="replace"))


def first_present(mapping: dict | sqlite3.Row, keys: list[str]) -> str | None:
    for key in keys:
        try:
            value = mapping[key]
        except (KeyError, IndexError):
            value = None
        if value not in {None, ""}:
            return str(value).strip()
    return None


def normalize_show_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", value)
    if not match:
        return None
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def date_tokens(show_date: str) -> list[str]:
    year, month, day = show_date.split("-")
    return [
        show_date,
        show_date.replace("-", "/"),
        f"{int(month)}/{int(day)}",
        f"{month}/{day}",
        f"{int(month)}月{int(day)}日",
        f"{month}月{day}日",
        f"{year}年{month}月{day}日",
    ]


def html_blocks_with_movie(soup: BeautifulSoup, aliases: list[str]) -> list[BeautifulSoup]:
    blocks: list[BeautifulSoup] = []
    for node in soup.find_all(string=True):
        if not movie_matches(str(node), aliases):
            continue
        parent = node.parent
        while parent and parent.name not in {"body", "[document]"}:
            text = parent.get_text(" ", strip=True)
            if len(text) > 80 or re.search(r"\d{1,2}:\d{2}", text):
                break
            parent = parent.parent
        if parent and parent not in blocks:
            blocks.append(parent)
    return blocks


def records_from_text_block(
    *,
    location_id: int,
    show_date: str,
    text: str,
    aliases: list[str],
    source_url: str,
    booking_url: str | None,
    format_text: str | None = None,
) -> list[ShowtimeRecord]:
    if not movie_matches(text, aliases):
        return []
    tokens = date_tokens(show_date)
    has_date = any(token in text for token in tokens)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title_line = next((line for line in lines if movie_matches(line, aliases)), format_text or "")
    records: list[ShowtimeRecord] = []

    for index, line in enumerate(lines):
        times = re.findall(r"\b\d{1,2}:\d{2}\b", line)
        if not times:
            continue
        nearby = "\n".join(lines[max(0, index - 8) : index + 9])
        if not has_date and not any(token in nearby for token in tokens):
            continue
        if not movie_matches(nearby, aliases) and (len(lines) > 30 or not movie_matches(text, aliases)):
            continue
        auditorium = None
        hall_match = re.search(r"([A-Za-z]?\d+\s*廳|[A-Za-z]+廳|BOOM\s*廳|LUXE\s*\d*廳|IMAX\s*廳|MX4D\s*廳)", nearby)
        if hall_match:
            auditorium = hall_match.group(1).replace(" ", "")
        for start_time in times:
            records.append(
                ShowtimeRecord(
                    location_id=location_id,
                    show_date=show_date,
                    start_time=start_time.zfill(5),
                    auditorium=auditorium,
                    format=format_text or title_line,
                    language=infer_language(format_text or title_line or nearby),
                    booking_url=booking_url,
                    source_url=source_url,
                    raw_text=title_line or nearby[:500],
                )
            )
    return records


def save_raw(source_name: str, content: bytes | str, suffix: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(TAIPEI).strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^\w.-]+", "_", source_name, flags=re.UNICODE).strip("_")
    path = OUTPUT_DIR / f"{timestamp}_{safe}.{suffix}"
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def get_movie_id(conn: sqlite3.Connection, title: str) -> int:
    row = conn.execute(
        """
        SELECT id
        FROM movies
        WHERE title = ?
          AND active = 1
        ORDER BY id DESC
        LIMIT 1
        """,
        (title,),
    ).fetchone()
    if row:
        return int(row["id"])

    conn.execute(
        """
        INSERT INTO movies (title, notes, active)
        VALUES (?, ?, 1)
        """,
        (title, "由 fetch_movie_showtimes.py 建立"),
    )
    row = conn.execute(
        """
        SELECT id
        FROM movies
        WHERE title = ?
          AND active = 1
        ORDER BY id DESC
        LIMIT 1
        """,
        (title,),
    ).fetchone()
    return int(row["id"])


def get_locations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            cl.id,
            cc.chain_name,
            cl.location_name,
            cl.source_location_code,
            cl.location_url,
            cc.crawl_url
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cl.active = 1
          AND cc.active = 1
        ORDER BY cc.chain_name, cl.location_name
        """
    ).fetchall()


def locations_by_chain_and_code(conn: sqlite3.Connection) -> dict[tuple[str, str], sqlite3.Row]:
    result = {}
    for row in get_locations(conn):
        code = row["source_location_code"]
        if code:
            result[(row["chain_name"], str(code))] = row
    return result


def start_run(conn: sqlite3.Connection, movie_id: int, source_name: str, source_url: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO crawl_runs (run_type, movie_id, source_name, source_url)
        VALUES ('showtimes', ?, ?, ?)
        """,
        (movie_id, source_name, source_url),
    )
    return int(cursor.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    rows_found: int,
    rows_saved: int,
    error_message: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE crawl_runs
        SET finished_at = CURRENT_TIMESTAMP,
            status = ?,
            rows_found = ?,
            rows_saved = ?,
            error_message = ?
        WHERE id = ?
        """,
        (status, rows_found, rows_saved, error_message, run_id),
    )


def save_showtimes(conn: sqlite3.Connection, movie_id: int, run_id: int, records: list[ShowtimeRecord]) -> int:
    saved = 0
    for record in records:
        conn.execute(
            """
            INSERT INTO showtimes (
                movie_id,
                location_id,
                crawl_run_id,
                show_date,
                start_time,
                auditorium,
                format,
                language,
                booking_url,
                source_url,
                raw_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(movie_id, location_id, show_date, start_time, ifnull(format, ''), ifnull(language, ''), ifnull(subtitle, ''), ifnull(booking_url, ''))
            DO UPDATE SET
                crawl_run_id = excluded.crawl_run_id,
                auditorium = excluded.auditorium,
                source_url = excluded.source_url,
                raw_text = excluded.raw_text
            """,
            (
                movie_id,
                record.location_id,
                run_id,
                record.show_date,
                record.start_time,
                record.auditorium,
                record.format,
                record.language,
                record.booking_url,
                record.source_url,
                record.raw_text,
            ),
        )
        saved += 1
    return saved


def fetch_showtimes_showtimes_api(
    conn: sqlite3.Connection,
    aliases: list[str],
    show_date: str,
) -> list[ShowtimeRecord]:
    payload = json.loads(
        request_text(
            SHOWTIMES_BOOTSTRAP_URL,
            headers={
                "Accept": "application/json,text/plain,*/*",
                "Origin": "https://www.showtimes.com.tw",
                "Referer": "https://www.showtimes.com.tw/",
            },
        )
    )["payload"]
    save_raw("showtimes_bootstrap", json.dumps(payload, ensure_ascii=False, indent=2), "json")

    program_by_id = {int(program["id"]): program for program in payload.get("programs", [])}
    target_ids = {
        program_id
        for program_id, program in program_by_id.items()
        if movie_matches(" ".join([str(program.get("name", "")), str(program.get("nameAlternative", ""))]), aliases)
    }
    locations = locations_by_chain_and_code(conn)
    records: list[ShowtimeRecord] = []

    for corporation_id, bundle in payload.get("eventsForCorporations", {}).items():
        location = locations.get(("秀泰影城", str(corporation_id)))
        if not location:
            continue
        venue_by_id = {int(venue["id"]): venue.get("room") for venue in bundle.get("venues", [])}
        booking_url = f"https://www.showtimes.com.tw/ticketing?cid={corporation_id}&date={show_date}&category=popular"
        for event in bundle.get("events", []):
            program_id = int(event.get("programId") or 0)
            if program_id not in target_ids:
                continue
            listed_at = str(event.get("listedAt", ""))
            if not listed_at.startswith(show_date):
                continue
            started_at = datetime.fromisoformat(str(event["startedAt"]).replace("Z", "+00:00")).astimezone(TAIPEI)
            meta = event.get("meta") or {}
            format_text = meta.get("format")
            program = program_by_id.get(program_id, {})
            records.append(
                ShowtimeRecord(
                    location_id=int(location["id"]),
                    show_date=show_date,
                    start_time=started_at.strftime("%H:%M"),
                    auditorium=venue_by_id.get(int(event.get("venueId") or 0)),
                    format=format_text,
                    language=infer_language(format_text),
                    booking_url=booking_url,
                    source_url=booking_url,
                    raw_text=f"{program.get('name', '')} {program.get('nameAlternative', '')} {format_text or ''} event={event.get('id')}",
                )
            )
    return records


def skcinemas_headers_from_request(headers: dict[str, str], entry_url: str) -> dict[str, str] | None:
    normalized = {str(key).lower(): value for key, value in headers.items()}
    if not all(normalized.get(key) for key in ("timestamp", "did", "token")):
        return None
    return {
        "timestamp": normalized["timestamp"],
        "DID": normalized["did"],
        "token": normalized["token"],
        "Referer": entry_url,
    }


def navigation_timeout_is_recoverable(error: Exception | None, captured: object) -> bool:
    return isinstance(error, PlaywrightTimeoutError) and bool(captured)


def capture_skcinemas_headers(
    entry_url: str, *, headless: bool | None = None, wait_ms: int = 8000
) -> dict[str, str]:
    captured: dict[str, str] = {}
    with sync_playwright() as playwright:
        if headless is None:
            headless = os.environ.get("SKCINEMAS_HEADLESS", "true").lower() not in {"0", "false", "no"}
        browser = playwright.chromium.launch(headless=headless, slow_mo=120 if not headless else 0)
        try:
            page = browser.new_page(
                user_agent=SKCINEMAS_USER_AGENT,
                locale="zh-TW",
                timezone_id="Asia/Taipei",
            )

            def on_request(request) -> None:
                nonlocal captured
                if captured or "/api/VistaDataV2/" not in request.url:
                    return
                headers = skcinemas_headers_from_request(request.headers, entry_url)
                if headers:
                    captured = headers

            # The signed API request can happen before DOMContentLoaded.
            page.on("request", on_request)
            navigation_error: Exception | None = None
            try:
                page.goto(entry_url, wait_until="commit", timeout=30_000)
            except PlaywrightTimeoutError as exc:
                navigation_error = exc

            deadline = time.monotonic() + wait_ms / 1000
            while not captured and time.monotonic() < deadline:
                page.wait_for_timeout(200)
            if navigation_error and not navigation_timeout_is_recoverable(navigation_error, captured):
                raise RuntimeError("無法取得新光 API headers（導航逾時且沒有 API request）") from navigation_error
        finally:
            browser.close()

    if not captured:
        raise RuntimeError("無法取得新光 API headers")
    return captured


def fetch_skcinemas(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    active_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '新光影城' AND cl.active = 1
        """
    ).fetchone()[0]
    rows = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '新光影城'
          AND cl.active = 1
          AND TRIM(COALESCE(cl.source_location_code, '')) <> ''
        ORDER BY cl.location_name
        """
    ).fetchall()
    if active_count and not rows:
        raise RuntimeError("新光影城有啟用據點，但 0 個據點具有 source_location_code")
    if not rows:
        return []

    entry_url = f"{SKCINEMAS_FILMS_URL}?c={rows[0]['source_location_code']}"
    headers = capture_skcinemas_headers(entry_url)
    records: list[ShowtimeRecord] = []
    for row in rows:
        cinema_id = str(row["source_location_code"])
        payload = request_json(
            SKCINEMAS_SESSION_API,
            method="POST",
            payload={"CustomerID": "", "Mobile": "", "CinemasID": cinema_id},
            headers=headers,
        )
        save_raw(f"skcinemas_sessions_{cinema_id}", json.dumps(payload, ensure_ascii=False, indent=2), "json")
        if not isinstance(payload, dict) or payload.get("result") is not True:
            raise RuntimeError(f"新光 API 回應失敗（據點 {cinema_id}）")
        data = payload.get("data") or {}
        session_films = data.get("SessionFilm") or []
        target_film_ids = {
            str(item.get("FilmNameID"))
            for item in session_films
            if movie_matches(" ".join([str(item.get("FilmName", "")), str(item.get("FilmType", ""))]), aliases)
        }
        for session in data.get("Session", []) or []:
            if str(session.get("FilmNameID")) not in target_film_ids:
                continue
            business_date = normalize_show_date(str(session.get("BusinessDate") or session.get("_businessDate") or ""))
            show_at = normalize_show_date(str(session.get("_showDate") or session.get("ShowDate") or ""))
            if show_date not in {business_date, show_at}:
                continue
            start_time = str(session.get("ShowTime", "")).strip()[:5]
            if not re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                continue
            format_text = first_present(session, ["FilmType"])
            records.append(
                ShowtimeRecord(
                    location_id=int(row["id"]),
                    show_date=show_date,
                    start_time=start_time.zfill(5),
                    auditorium=first_present(session, ["ScreenName", "ScreenEName"]),
                    format=format_text,
                    language=infer_language(format_text),
                    booking_url=f"{SKCINEMAS_FILMS_URL}?c={cinema_id}",
                    source_url=SKCINEMAS_SESSION_API,
                    raw_text=f"{session.get('FilmNameID', '')} {format_text or ''} session={session.get('SessionID')}",
                )
            )
    return records


def in89_api_host(location_url: str, fallback_code: str) -> str | None:
    text = request_text(location_url, headers={"Referer": "https://www.in89cinemax.com/"}, verify_ssl=False)
    match = re.search(r'name=["\']theater_api["\']\s+value=["\']([^"\']+)["\']', text)
    if match:
        return match.group(1)
    fallback_hosts = {
        "1": "taoyuan.in89.com.tw",
        "2": "pier2.in89.com.tw",
        "3": "taipei.in89.com.tw",
        "14": "penghu.in89.com.tw",
        "15": "fengyuan.in89.com.tw",
        "16": "talee.in89.com.tw",
        "17": "chiayi.in89.com.tw",
    }
    return fallback_hosts.get(fallback_code)


def fetch_in89(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    rows = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = 'in89 豪華影城'
          AND cl.active = 1
          AND cl.source_location_code IS NOT NULL
        ORDER BY cl.location_name
        """
    ).fetchall()
    records: list[ShowtimeRecord] = []
    for row in rows:
        code = str(row["source_location_code"])
        location_url = row["location_url"] or f"https://www.in89cinemax.com/film_list.aspx?TheaterId={code}"
        host = in89_api_host(location_url, code)
        if not host:
            continue
        source_url = f"https://{host}{IN89_API_PATH}"
        payload = request_json(source_url, headers={"Referer": location_url}, verify_ssl=False)
        save_raw(f"in89_{code}_stages", json.dumps(payload, ensure_ascii=False, indent=2), "json")
        if not isinstance(payload, dict):
            continue
        movies = payload.get("movies") or {}
        target_movie_ids = {
            str(movie_id)
            for movie_id, movie in movies.items()
            if movie_matches(
                " ".join(
                    str(movie.get(key, ""))
                    for key in ["movie_group_name", "en_name", "movie_play_desc", "movie_lang_desc"]
                ),
                aliases,
            )
        }
        stages = payload.get("stages") or {}
        for date_key, by_start in stages.items():
            if normalize_show_date(str(date_key)) != show_date:
                continue
            if not isinstance(by_start, dict):
                continue
            for by_cn in by_start.values():
                if not isinstance(by_cn, dict):
                    continue
                for by_movie in by_cn.values():
                    if not isinstance(by_movie, dict):
                        continue
                    for movie_id, stage_items in by_movie.items():
                        if str(movie_id) not in target_movie_ids:
                            continue
                        movie_info = movies.get(str(movie_id), {})
                        for stage in stage_items or []:
                            start_value = first_present(stage, ["movie_show_time", "show_time", "start_time"])
                            match = re.search(r"\d{1,2}:\d{2}", start_value or "")
                            if not match:
                                continue
                            format_text = first_present(stage, ["theater_film_name", "movie_play_desc"]) or " ".join(
                                str(movie_info.get(key, ""))
                                for key in ["movie_play_desc", "movie_lang_desc"]
                                if movie_info.get(key)
                            )
                            records.append(
                                ShowtimeRecord(
                                    location_id=int(row["id"]),
                                    show_date=show_date,
                                    start_time=match.group(0).zfill(5),
                                    auditorium=first_present(stage, ["room_name", "field_name", "hall_name", "room"]),
                                    format=format_text or None,
                                    language=infer_language(
                                        " ".join([format_text or "", str(movie_info.get("movie_lang_desc", ""))])
                                    ),
                                    booking_url=location_url,
                                    source_url=source_url,
                                    raw_text=" ".join(
                                        str(movie_info.get(key, ""))
                                        for key in ["movie_group_name", "en_name", "movie_play_desc", "movie_lang_desc"]
                                        if movie_info.get(key)
                                    ),
                                )
                            )
    return records


def ambassador_url(location_code: str, show_date: str) -> str:
    dt = urllib.parse.quote(show_date.replace("-", "/"), safe="/")
    return f"https://www.ambassador.com.tw/home/Showtime?ID={location_code}&DT={dt}"


def fetch_ambassador_location(location: sqlite3.Row, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    source_url = ambassador_url(str(location["source_location_code"]), show_date)
    text = request_text(source_url, headers={"Referer": "https://www.ambassador.com.tw/home/TheaterList"})
    save_raw(f"ambassador_{location['id']}", text, "html")
    soup = BeautifulSoup(text, "html.parser")
    records: list[ShowtimeRecord] = []

    for item in soup.select(".showtime-item"):
        item_text = item.get_text(" ", strip=True)
        if not movie_matches(item_text, aliases):
            continue
        title_node = item.select_one("h3 a")
        tag_node = item.select_one(".tag-seat")
        format_text = tag_node.get_text(" ", strip=True) if tag_node else None
        for li in item.select("ul.seat-list li"):
            time_node = li.find("h6")
            if not time_node:
                continue
            start_time = time_node.get_text(" ", strip=True)
            if not re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                continue
            info_node = li.select_one(".info")
            records.append(
                ShowtimeRecord(
                    location_id=int(location["id"]),
                    show_date=show_date,
                    start_time=start_time.zfill(5),
                    auditorium=info_node.get_text(" ", strip=True) if info_node else None,
                    format=format_text,
                    language=infer_language(format_text),
                    booking_url=source_url,
                    source_url=source_url,
                    raw_text=f"{title_node.get_text(' ', strip=True) if title_node else ''} {format_text or ''}",
                )
            )
    return records


def fetch_ambassador(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    rows = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '國賓影城'
          AND cl.active = 1
          AND cl.source_location_code IS NOT NULL
        ORDER BY cl.location_name
        """
    ).fetchall()
    records: list[ShowtimeRecord] = []
    for row in rows:
        records.extend(fetch_ambassador_location(row, aliases, show_date))
    return records


def extract_miranew_payload(text: str) -> dict:
    match = re.search(r"var\s+CinemaList\s*=\s*'(.*?)';", text, flags=re.S)
    if not match:
        return {}
    json_text = ast.literal_eval("'" + match.group(1) + "'")
    return json.loads(json_text)


def fetch_miranew(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    text = request_text(MIRANEW_TIMETABLE_URL, headers={"Referer": "https://www.miranewcinemas.com/"})
    save_raw("miranew_timetable", text, "html")
    payload = extract_miranew_payload(text)
    locations = locations_by_chain_and_code(conn)
    records: list[ShowtimeRecord] = []

    for cinema in payload.get("Data", {}).get("CinemaGroup", []):
        location = locations.get(("美麗新影城", str(cinema.get("CinemaId"))))
        if not location:
            continue
        for movie in cinema.get("MovieInfo", []):
            title_text = " ".join([str(movie.get("MovieCName", "")), str(movie.get("MovieEName", ""))])
            if not movie_matches(title_text, aliases):
                continue
            for show_date_item in movie.get("ShowDateList", []):
                iso_date = str(show_date_item.get("ShowDateISO", ""))[:10]
                if iso_date != show_date:
                    continue
                for hall_group in show_date_item.get("ShowTimeList", []):
                    format_text = hall_group.get("MovieHallCht") or hall_group.get("MovieHallEn")
                    for session in hall_group.get("SessionList", []):
                        start_time = str(session.get("ShowTime", "")).strip()
                        if not re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                            continue
                        records.append(
                            ShowtimeRecord(
                                location_id=int(location["id"]),
                                show_date=show_date,
                                start_time=start_time.zfill(5),
                                auditorium=session.get("MovieHallCode"),
                                format=format_text,
                                language=infer_language(format_text),
                                booking_url=MIRANEW_TIMETABLE_URL,
                                source_url=MIRANEW_TIMETABLE_URL,
                                raw_text=f"{title_text} {format_text or ''} session={session.get('SessionId')}",
                            )
                        )
    return records


def fetch_ccmovie(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '親親影城 / 親親戲院'
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []
    raw = request_bytes(CCMOVIE_URL, headers={"Referer": "https://www.ccmovie.com.tw/"})
    save_raw("ccmovie_showtimes", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records: list[ShowtimeRecord] = []

    for title in soup.select(".m_title"):
        if not movie_matches(title.get_text(" ", strip=True), aliases):
            continue
        box = title.find_parent(class_="theater-box")
        if not box:
            continue
        target_tab = box.find(id=re.compile(re.escape(show_date)))
        if not target_tab:
            continue
        current_format: str | None = None
        for child in target_tab.find_all(recursive=False):
            classes = child.get("class") or []
            if "dateMovie" in classes:
                current_format = child.get_text(" ", strip=True).replace("", "").strip()
            elif "movie_showtimes" in classes:
                for time_node in child.select(".sky_word .info"):
                    start_time = time_node.get_text(" ", strip=True)
                    if re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                        records.append(
                            ShowtimeRecord(
                                location_id=int(row["id"]),
                                show_date=show_date,
                                start_time=start_time.zfill(5),
                                auditorium=None,
                                format=current_format,
                                language=infer_language(current_format),
                                booking_url=CCMOVIE_URL,
                                source_url=CCMOVIE_URL,
                                raw_text=f"{title.get_text(' ', strip=True)} {current_format or ''}",
                            )
                        )
    return records


def fetch_acecinema(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '王牌映画影城'
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []
    raw = request_bytes(ACE_URL, headers={"Referer": "https://www.acecinema.com.tw/"})
    save_raw("acecinema_now", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records: list[ShowtimeRecord] = []

    for movie in soup.select(".movie_list"):
        title_node = movie.select_one(".txt > h3")
        alt_node = movie.select_one(".txt > h4")
        title_text = " ".join(
            node.get_text(" ", strip=True)
            for node in [title_node, alt_node]
            if node
        )
        if not movie_matches(title_text, aliases):
            continue
        date_heading = movie.find("h3", class_="txt_blue")
        if date_heading and show_date.replace("-", "/") not in date_heading.get_text(" ", strip=True):
            continue
        format_text = title_node.get_text(" ", strip=True) if title_node else None
        for button in movie.select(".btn_session"):
            start_node = button.find("span")
            if not start_node:
                continue
            start_time = start_node.get_text(" ", strip=True)
            auditorium = button.get_text(" ", strip=True).replace(start_time, "").strip("  ")
            if re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                records.append(
                    ShowtimeRecord(
                        location_id=int(row["id"]),
                        show_date=show_date,
                        start_time=start_time.zfill(5),
                        auditorium=auditorium or None,
                        format=format_text,
                        language=infer_language(format_text),
                        booking_url=ACE_URL,
                        source_url=ACE_URL,
                        raw_text=title_text,
                    )
                )
    return records


def fetch_broadway(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    rows = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '百老匯影城'
          AND cl.active = 1
          AND cl.source_location_code IS NOT NULL
        ORDER BY cl.location_name
        """
    ).fetchall()
    records: list[ShowtimeRecord] = []
    for row in rows:
        code = str(row["source_location_code"])
        source_url = BROADWAY_API.format(code=code)
        text = request_text(
            source_url,
            headers={
                "Accept": "application/json,text/plain,*/*",
                "Referer": f"https://www.broadway-cineplex.com.tw/book.html?obj={code}&v25080101",
            },
            verify_ssl=False,
        )
        save_raw(f"broadway_{code}", text, "json")
        payload = json.loads(text)
        for movie in payload.get("Data", []):
            if not movie_matches(" ".join([str(movie.get("cname", "")), str(movie.get("ename", ""))]), aliases):
                continue
            for group in movie.get("timedata", []):
                format_text = group.get("SubName2")
                for item in group.get("subtimedata", []):
                    if item.get("showdate") != show_date:
                        continue
                    start_time = str(item.get("時間", "")).strip()
                    if not re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                        continue
                    records.append(
                        ShowtimeRecord(
                            location_id=int(row["id"]),
                            show_date=show_date,
                            start_time=start_time.zfill(5),
                            auditorium=item.get("hallname"),
                            format=format_text,
                            language=infer_language(format_text),
                            booking_url=f"https://www.broadway-cineplex.com.tw/book.html?obj={code}&v25080101",
                            source_url=source_url,
                            raw_text=f"{movie.get('cname', '')} {movie.get('ename', '')} {format_text or ''}",
                        )
                    )
    return records


def text_blocks_from_html(raw: bytes | str) -> list[str]:
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8" if isinstance(raw, bytes) else None)
    text = soup.get_text("\n", strip=True)
    return [line.strip() for line in text.splitlines() if line.strip()]


def fetch_centuryasia(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    rows = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '喜樂時代影城'
          AND cl.active = 1
        ORDER BY cl.location_name
        """
    ).fetchall()
    records: list[ShowtimeRecord] = []
    for row in rows:
        source_url = row["location_url"] or CENTURYASIA_URL
        html_text = render_page_html(source_url, wait_ms=6000)
        save_raw(f"centuryasia_{row['source_location_code'] or row['id']}", html_text, "html")
        soup = BeautifulSoup(html_text, "html.parser")
        page_text = soup.get_text("\n", strip=True)
        if not movie_matches(page_text, aliases):
            continue
        for block in html_blocks_with_movie(soup, aliases):
            block_text = block.get_text("\n", strip=True)
            records.extend(
                records_from_text_block(
                    location_id=int(row["id"]),
                    show_date=show_date,
                    text=block_text,
                    aliases=aliases,
                    source_url=source_url,
                    booking_url=source_url,
                )
            )
    return records


def fetch_tmovies(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '天台影城'
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []
    raw = request_bytes(TMOVIES_URL, headers={"Referer": "https://www.t-movies.com.tw/"}, verify_ssl=False)
    save_raw("tmovies_index", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records: list[ShowtimeRecord] = []
    for block in html_blocks_with_movie(soup, aliases):
        records.extend(
            records_from_text_block(
                location_id=int(row["id"]),
                show_date=show_date,
                text=block.get_text("\n", strip=True),
                aliases=aliases,
                source_url=TMOVIES_URL,
                booking_url=TMOVIES_URL,
            )
        )
    return records


def fetch_halar(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    """解析哈拉影城單館時刻表；每部電影區塊會依日期列出場次。"""
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '哈拉影城' AND cl.active = 1
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []

    # 哈拉站的憑證缺少 Subject Key Identifier，Python 的嚴格 TLS 驗證會拒絕；
    # 僅此官方來源沿用其他既有來源的相容處理。
    raw = request_bytes(HALAR_URL, verify_ssl=False)
    save_raw("halar_showtimes", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records: list[ShowtimeRecord] = []
    for film in soup.select(".film-item"):
        title_node = film.select_one(".film-title")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if not movie_matches(title, aliases):
            continue
        for session in film.select(".session"):
            date_node = session.select_one(".session-date")
            if not date_node or normalize_show_date(date_node.get_text(" ", strip=True)) != show_date:
                continue
            for time_link in session.select("a.session-time"):
                time_node = time_link.select_one("time")
                if not time_node:
                    continue
                start_time = time_node.get_text(strip=True)
                if not re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                    continue
                href = time_link.get("href") or HALAR_URL
                booking_url = urllib.parse.urljoin(HALAR_URL, href)
                attributes = [image.get("alt", "").strip() for image in time_link.select("img[alt]")]
                auditorium = " / ".join(value for value in attributes if value) or None
                records.append(
                    ShowtimeRecord(
                        location_id=int(row["id"]),
                        show_date=show_date,
                        start_time=start_time.zfill(5),
                        auditorium=auditorium,
                        format=title,
                        language=infer_language(title),
                        booking_url=booking_url,
                        source_url=HALAR_URL,
                        raw_text=f"{title} | {date_node.get_text(' ', strip=True)} | {start_time}",
                    )
                )
    return records


def fetch_miramar(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    """解析美麗華影城時刻表；每部電影以場次日期與影廳/語言分組。"""
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '美麗華影城' AND cl.active = 1
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []

    raw = request_bytes(MIRAMAR_URL)
    save_raw("miramar_showtimes", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    wanted_month_day = tuple(int(value) for value in show_date.split("-")[1:])
    records: list[ShowtimeRecord] = []

    for movie in soup.select(".timetable_list"):
        title_node = movie.select_one(".movie_info .title")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if not movie_matches(title, aliases):
            continue
        for block in movie.select(".time_list_right > .block"):
            classes = " ".join(block.get("class", []))
            date_match = re.search(r"(\d{1,2})月(\d{1,2})日", classes)
            if not date_match or (int(date_match.group(1)), int(date_match.group(2))) != wanted_month_day:
                continue
            room_node = block.select_one(".room")
            room = room_node.get_text(" ", strip=True).replace("watch_later", "").strip() if room_node else None
            for time_link in block.select("a.booking_time"):
                start_time = time_link.get_text(strip=True)
                if not re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                    continue
                booking_url = urllib.parse.urljoin(MIRAMAR_URL, time_link.get("href") or MIRAMAR_URL)
                records.append(
                    ShowtimeRecord(
                        location_id=int(row["id"]),
                        show_date=show_date,
                        start_time=start_time.zfill(5),
                        auditorium=None,
                        format=room,
                        language=infer_language(room),
                        booking_url=booking_url,
                        source_url=MIRAMAR_URL,
                        raw_text=f"{title} | {classes} | {room or ''} | {start_time}",
                    )
                )
    return records


def fetch_nantai(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    """解析南台影城依日期選單切換的單館時刻表。"""
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '南台影城' AND cl.active = 1
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []

    source_url = NANTAI_URL
    raw = request_bytes(source_url)
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    # 選單 value 是站內日期索引；先由首頁找出指定日期，再抓取該日頁面。
    target_option = next(
        (option for option in soup.select("#showtime_search option") if show_date in option.get_text(" ", strip=True)),
        None,
    )
    if target_option is None:
        return []
    day_value = (target_option.get("value") or "").strip()
    if day_value:
        source_url = f"{NANTAI_URL}?day={urllib.parse.quote(day_value)}"
        raw = request_bytes(source_url)
        soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    save_raw("nantai_showtimes", raw, "html")

    records: list[ShowtimeRecord] = []
    for movie in soup.select("#movieList > li"):
        title_node = movie.select_one(".movieTitle")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if not movie_matches(title, aliases):
            continue
        for time_node in movie.select("ul.times > li"):
            start_time = time_node.get_text(strip=True)
            if not re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                continue
            records.append(
                ShowtimeRecord(
                    location_id=int(row["id"]),
                    show_date=show_date,
                    start_time=start_time.zfill(5),
                    auditorium=None,
                    format=title,
                    language=infer_language(title),
                    booking_url=source_url,
                    source_url=source_url,
                    raw_text=f"{title} | {start_time}",
                )
            )
    return records


def fetch_lux(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    """解析樂聲影城單館時刻表，保留電影版本與 L/XL 廳別。"""
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '樂聲影城' AND cl.active = 1
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []

    raw = request_bytes(LUX_URL)
    save_raw("lux_showtimes", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    wanted_month_day = tuple(int(value) for value in show_date.split("-")[1:])
    records: list[ShowtimeRecord] = []

    for movie in soup.select(".movie_list_box"):
        title_node = movie.select_one("h1")
        if not title_node:
            continue
        title = title_node.get_text(" ", strip=True).replace("立即訂票", "").strip()
        if not movie_matches(title, aliases):
            continue
        movie_link = movie.find_parent("a", href=True)
        booking_url = urllib.parse.urljoin(LUX_URL, movie_link["href"]) if movie_link else LUX_URL
        for date_node in movie.select("h3"):
            date_match = re.search(r"(\d{1,2})/(\d{1,2})", date_node.get_text(" ", strip=True))
            if not date_match or (int(date_match.group(1)), int(date_match.group(2))) != wanted_month_day:
                continue
            times_node = date_node.find_next_sibling("ul")
            if not times_node:
                continue
            for item in times_node.select("li"):
                match = re.search(r"(\d{1,2}:\d{2})(?:\s*\|\s*([A-Za-z0-9]+))?", item.get_text(" ", strip=True))
                if not match:
                    continue
                records.append(
                    ShowtimeRecord(
                        location_id=int(row["id"]),
                        show_date=show_date,
                        start_time=match.group(1).zfill(5),
                        auditorium=match.group(2),
                        format=title,
                        language=infer_language(title),
                        booking_url=booking_url,
                        source_url=LUX_URL,
                        raw_text=f"{title} | {date_node.get_text(' ', strip=True)} | {item.get_text(' ', strip=True)}",
                    )
                )
    return records


def fetch_mld(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    """解析台鋁影城時刻表，保留電影版本與個別訂票連結。"""
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '台鋁影城' AND cl.active = 1
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []

    raw = request_bytes(MLD_URL)
    save_raw("mld_showtimes", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records: list[ShowtimeRecord] = []
    for movie in soup.select(".timesList .showingBox"):
        title_node = movie.select_one(".photoBox .title")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if not movie_matches(title, aliases):
            continue
        for day in movie.select(".dateBox .item dl"):
            date_node = day.find("dt")
            if not date_node or normalize_show_date(date_node.get_text(" ", strip=True)) != show_date:
                continue
            for time_link in day.select("dd a"):
                start_time = time_link.get_text(strip=True)
                if not re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                    continue
                onclick = time_link.get("onclick") or ""
                booking_match = re.search(r"LinkAlert\('([^']+)'", onclick)
                booking_url = urllib.parse.urljoin(MLD_URL, booking_match.group(1) if booking_match else time_link.get("href") or MLD_URL)
                records.append(
                    ShowtimeRecord(
                        location_id=int(row["id"]),
                        show_date=show_date,
                        start_time=start_time.zfill(5),
                        auditorium=None,
                        format=title,
                        language=infer_language(title),
                        booking_url=booking_url,
                        source_url=MLD_URL,
                        raw_text=f"{title} | {date_node.get_text(' ', strip=True)} | {start_time}",
                    )
                )
    return records


def fetch_tixi(
    conn: sqlite3.Connection,
    aliases: list[str],
    show_date: str,
    *,
    chain_name: str,
    source_url: str,
) -> list[ShowtimeRecord]:
    """解析 TIXI 票務頁，依場次參數的完整日期過濾。"""
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = ? AND cl.active = 1
        LIMIT 1
        """
        ,
        (chain_name,),
    ).fetchone()
    if not row:
        return []

    raw = request_bytes(source_url)
    save_raw(f"tixi_showtimes_{row['id']}", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records: list[ShowtimeRecord] = []
    for movie in soup.select("#selMovie .card"):
        title_node = movie.select_one(".movie_info .movie_title")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if not movie_matches(title, aliases):
            continue
        for room in movie.select(".movie_times .room"):
            room_text = room.get_text(" ", strip=True)
            times = room.find_next_sibling("ul", class_="btn_time")
            if not times:
                continue
            hall_match = re.search(r"((?:A\s+)?(?:One|Two)\s*廳|[A-Za-z]\s*廳|\d+\s*廳)", room_text, re.IGNORECASE)
            auditorium = hall_match.group(1).replace(" ", "") if hall_match else None
            language = "國語" if re.search(r"(?:-|\s)國(?:\s|$)", room_text) else infer_language(room_text)
            for time_link in times.select("a"):
                onclick = time_link.get("onclick") or ""
                match = re.search(r"SetCorp\('([0-9]{4}/[0-9]{2}/[0-9]{2})\s+(\d{1,2}:\d{2}):\d{2}_[^']+'\)", onclick)
                if not match or match.group(1).replace("/", "-") != show_date:
                    continue
                start_time = match.group(2)
                records.append(
                    ShowtimeRecord(
                        location_id=int(row["id"]),
                        show_date=show_date,
                        start_time=start_time.zfill(5),
                        auditorium=auditorium,
                        format=room_text,
                        language=language,
                        booking_url=source_url,
                        source_url=source_url,
                        raw_text=f"{title} | {room_text} | {start_time}",
                    )
                )
    return records


def fetch_machi(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    return fetch_tixi(
        conn,
        aliases,
        show_date,
        chain_name="鴻金寶麻吉影城",
        source_url=MACHI_URL,
    )


def fetch_spot_hs(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    return fetch_tixi(
        conn,
        aliases,
        show_date,
        chain_name="光點華山電影館",
        source_url=SPOT_HS_URL,
    )


def fetch_breeze(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    return fetch_tixi(
        conn,
        aliases,
        show_date,
        chain_name="微風影城",
        source_url=BREEZE_URL,
    )


def fetch_governor(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    return fetch_tixi(
        conn,
        aliases,
        show_date,
        chain_name="總督數位影城",
        source_url=GOVERNOR_URL,
    )


def fetch_eslite(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    """解析誠品電影院依電影卡片列出的多日場次。"""
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '誠品電影院' AND cl.active = 1
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []

    raw = request_bytes(ESLITE_URL)
    save_raw("eslite_showtimes", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    booking_node = next((node for node in soup.find_all("a", href=True) if node.get_text(" ", strip=True) == "訂票"), None)
    booking_url = booking_node.get("href") if booking_node else ESLITE_URL
    wanted_month_day = tuple(int(value) for value in show_date.split("-")[1:])
    records: list[ShowtimeRecord] = []

    for movie in soup.select(".film_list > .box"):
        title_node = movie.select_one(".intro .left > p")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if not movie_matches(title, aliases):
            continue
        for day in movie.select(".time-swiper .swiper-slide"):
            date_node = day.find("p")
            if not date_node:
                continue
            date_match = re.search(r"(\d{1,2})/(\d{1,2})", date_node.get_text(" ", strip=True))
            if not date_match or (int(date_match.group(1)), int(date_match.group(2))) != wanted_month_day:
                continue
            for item in day.select("ul > li"):
                start_time = item.get_text(" ", strip=True)
                if not re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                    continue
                records.append(
                    ShowtimeRecord(
                        location_id=int(row["id"]),
                        show_date=show_date,
                        start_time=start_time.zfill(5),
                        auditorium=None,
                        format=title,
                        language=infer_language(title),
                        booking_url=booking_url,
                        source_url=ESLITE_URL,
                        raw_text=f"{title} | {date_node.get_text(' ', strip=True)} | {start_time}",
                    )
                )
    return records


def fetch_nantou(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    """解析南投戲院依 search_date 切換的每日場次與個別訂票連結。"""
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '南投戲院' AND cl.active = 1
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []

    source_url = NANTOU_URL.format(show_date=show_date)
    raw = request_bytes(source_url)
    save_raw("nantou_showtimes", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records: list[ShowtimeRecord] = []
    for title_node in soup.select("h4"):
        title = title_node.get_text(" ", strip=True)
        if not movie_matches(title, aliases):
            continue
        auditorium = None
        for sibling in title_node.next_siblings:
            if getattr(sibling, "name", None) == "h4":
                break
            text = sibling.get_text(" ", strip=True) if getattr(sibling, "get_text", None) else str(sibling).strip()
            hall_match = re.search(r"廳別：\s*([^\s]+\s*廳)", text)
            if hall_match:
                auditorium = hall_match.group(1).replace(" ", "")
            if not getattr(sibling, "name", None) == "a":
                continue
            start_time = sibling.get_text(" ", strip=True)
            if not re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                continue
            records.append(
                ShowtimeRecord(
                    location_id=int(row["id"]),
                    show_date=show_date,
                    start_time=start_time.zfill(5),
                    auditorium=auditorium,
                    format=title,
                    language=infer_language(title),
                    # 個別訂票頁會要求登入；地圖入口應維持可直接開啟的每日時刻表。
                    booking_url=source_url,
                    source_url=source_url,
                    raw_text=f"{title} | {auditorium or ''} | {start_time}",
                )
            )
    return records


def fetch_shanming(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    """先找電影 id，再解析埔里山明影城時刻頁的有效日期範圍與場次。"""
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '埔里山明影城' AND cl.active = 1
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []

    raw = request_bytes(SHANMING_URL)
    save_raw("shanming_movies", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records: list[ShowtimeRecord] = []
    wanted_date = datetime.strptime(show_date, "%Y-%m-%d").date()

    for movie_link in soup.select("ul.all-movies a.list[href]"):
        title = movie_link.get_text(" ", strip=True)
        if not movie_matches(title, aliases):
            continue
        detail_url = urllib.parse.urljoin(SHANMING_URL, movie_link["href"])
        detail = request_bytes(detail_url)
        save_raw("shanming_showtimes", detail, "html")
        detail_soup = BeautifulSoup(detail, "html.parser", from_encoding="utf-8")
        range_node = detail_soup.select_one(".showtimes-list .title")
        if not range_node:
            continue
        date_parts = re.findall(r"(\d{1,2})月(\d{1,2})日", range_node.get_text(" ", strip=True))
        if len(date_parts) < 2:
            continue
        start_month, start_day = (int(value) for value in date_parts[0])
        end_month, end_day = (int(value) for value in date_parts[1])
        start_date = date(wanted_date.year, start_month, start_day)
        end_date = date(wanted_date.year, end_month, end_day)
        if end_date < start_date:
            end_date = date(wanted_date.year + 1, end_month, end_day)
        if not start_date <= wanted_date <= end_date:
            continue

        for item in detail_soup.select(".showtimes-list i.item"):
            match = re.search(r"(\d{1,2}:\d{2})\s*([中英日韓]?)(?:\(([^)]+)\))?", item.get_text(" ", strip=True))
            if not match:
                continue
            language = {"中": "國語", "英": "英語", "日": "日語", "韓": "韓語"}.get(match.group(2))
            records.append(
                ShowtimeRecord(
                    location_id=int(row["id"]),
                    show_date=show_date,
                    start_time=match.group(1).zfill(5),
                    auditorium=match.group(3),
                    format=title,
                    language=language or infer_language(title),
                    booking_url=detail_url,
                    source_url=detail_url,
                    raw_text=f"{title} | {range_node.get_text(' ', strip=True)} | {item.get_text(' ', strip=True)}",
                )
            )
    return records


def fetch_timescinema(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    """解析清水時代影城首頁所指向的時刻表批次，依 1館／2館分派據點。"""
    rows = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '清水時代影城' AND cl.active = 1
        """
    ).fetchall()
    if not rows:
        return []
    locations = {"1": next((row for row in rows if "一館" in row["location_name"]), None), "2": next((row for row in rows if "二館" in row["location_name"]), None)}

    homepage = BeautifulSoup(request_bytes("https://www.timescinema.com.tw/").decode("utf-8", errors="replace"), "html.parser")
    current_link = next(
        (
            anchor.get("href")
            for anchor in homepage.select("a[href]")
            if re.search(r"showtimes=\d+", anchor.get("href", ""))
        ),
        None,
    )
    if not current_link:
        return []
    current_url = urllib.parse.urljoin(TIMES_URL, current_link)
    current_raw = request_bytes(current_url)
    current_soup = BeautifulSoup(current_raw.decode("utf-8", errors="replace"), "html.parser")
    pages: dict[str, str] = {current_url: (current_soup.select_one(".showtimes_list2") or current_soup).get_text(" ", strip=True)}
    for anchor in current_soup.select("a.showtimes_list[href]"):
        pages[urllib.parse.urljoin(current_url, anchor["href"])] = anchor.get_text(" ", strip=True)

    wanted_date = datetime.strptime(show_date, "%Y-%m-%d").date()
    records: list[ShowtimeRecord] = []
    for page_url, range_text in pages.items():
        date_parts = re.findall(r"(\d{1,2})月(\d{1,2})日", range_text)
        if len(date_parts) < 2:
            continue
        start_month, start_day = (int(value) for value in date_parts[0])
        end_month, end_day = (int(value) for value in date_parts[1])
        start_date = date(wanted_date.year, start_month, start_day)
        end_date = date(wanted_date.year, end_month, end_day)
        if end_date < start_date:
            end_date = date(wanted_date.year + 1, end_month, end_day)
        if not start_date <= wanted_date <= end_date:
            continue
        if page_url == current_url:
            soup = current_soup
            raw = current_raw
        else:
            raw = request_bytes(page_url)
            soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")
        save_raw("timescinema_showtimes", raw, "html")

        for movie in soup.select(".times_sort"):
            title_node = movie.select_one(".times_sort_title")
            title = title_node.get_text(" ", strip=True) if title_node else ""
            if not movie_matches(title, aliases):
                continue
            content = movie.select_one(".times_sort_content")
            if not content:
                continue
            default_halls = re.findall(r"([12])館\s*[A-Za-z]廳", content.get_text(" ", strip=True))
            default_hall = default_halls[0] if len(set(default_halls)) == 1 else None
            for table_row in content.select("table tr"):
                pending: list[tuple[str, str | None]] = []
                for cell in table_row.select("td"):
                    cell_text = cell.get_text(" ", strip=True)
                    hall_match = re.search(r"[→]?\s*([12])館\s*([A-Za-z]廳)", cell_text)
                    if hall_match:
                        hall_key = hall_match.group(1)
                        location = locations.get(hall_key)
                        if location:
                            for start_time, language in pending:
                                records.append(
                                    ShowtimeRecord(int(location["id"]), show_date, start_time.zfill(5), f"{hall_key}館{hall_match.group(2)}", title, language or infer_language(title), page_url, page_url, f"{title} | {range_text} | {cell_text}")
                                )
                        pending.clear()
                        continue
                    time_match = re.search(r"(\d{1,2}:\d{2})", cell_text)
                    if time_match:
                        language = "國語" if "中文" in cell_text else "英語" if "英文" in cell_text else "日語" if "日文" in cell_text else None
                        pending.append((time_match.group(1), language))
                if pending and default_hall and locations.get(default_hall):
                    location = locations[default_hall]
                    hall_letter = next(iter(re.findall(rf"{default_hall}館\s*([A-Za-z]廳)", content.get_text(" ", strip=True))), "")
                    for start_time, language in pending:
                        records.append(
                            ShowtimeRecord(int(location["id"]), show_date, start_time.zfill(5), f"{default_hall}館{hall_letter}", title, language or infer_language(title), page_url, page_url, f"{title} | {range_text} | {start_time}")
                        )
    return records


def fetch_venice(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '威尼斯影城'
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []
    records: list[ShowtimeRecord] = []
    for page_number in range(1, 5):
        source_url = VENICE_URL.format(page=page_number)
        try:
            html_text = render_page_html(source_url, wait_ms=4000)
        except Exception:
            continue
        save_raw(f"venice_showtime_{page_number}", html_text, "html")
        soup = BeautifulSoup(html_text, "html.parser")
        if not movie_matches(soup.get_text("\n", strip=True), aliases):
            continue
        for block in html_blocks_with_movie(soup, aliases):
            records.extend(
                records_from_text_block(
                    location_id=int(row["id"]),
                    show_date=show_date,
                    text=block.get_text("\n", strip=True),
                    aliases=aliases,
                    source_url=source_url,
                    booking_url=source_url,
                )
            )
    return records


def fetch_uch(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '環球中華影城'
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []
    raw = request_bytes(UCH_URL, headers={"Referer": "https://www.uch-movies.tw/"}, verify_ssl=False)
    save_raw("uch_time", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records: list[ShowtimeRecord] = []
    for block in html_blocks_with_movie(soup, aliases):
        records.extend(
            records_from_text_block(
                location_id=int(row["id"]),
                show_date=show_date,
                text=block.get_text("\n", strip=True),
                aliases=aliases,
                source_url=UCH_URL,
                booking_url=UCH_URL,
            )
        )
    return records


def fetch_umovie(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '高雄環球影城'
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []
    raw = request_bytes(UMOVIE_URL, headers={"Referer": "https://www.u-movie.com.tw/"})
    save_raw("umovie_now", raw, "html")
    lines = text_blocks_from_html(raw)
    blocks = "\n".join(lines).split("《查詢更多場次》")
    records: list[ShowtimeRecord] = []
    for block in blocks:
        if not movie_matches(block, aliases) or show_date not in block:
            continue
        title_line = next((line for line in block.splitlines() if movie_matches(line, aliases)), "")
        format_text = title_line.replace("Toy Story 5", "").strip() or title_line
        for match in re.finditer(r"(?m)^(\d{1,2}:\d{2})\s*$\s*^([^\n]*廳[^\n]*)", block):
            records.append(
                ShowtimeRecord(
                    location_id=int(row["id"]),
                    show_date=show_date,
                    start_time=match.group(1).zfill(5),
                    auditorium=match.group(2).strip(),
                    format=format_text,
                    language=infer_language(format_text),
                    booking_url=UMOVIE_URL,
                    source_url=UMOVIE_URL,
                    raw_text=title_line,
                )
            )
    return records


def fetch_luna(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '新月豪華影城'
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []
    raw = request_bytes(LUNA_URL, headers={"Referer": "https://www.lunacinemax.com.tw/"})
    save_raw("luna_schedule", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records: list[ShowtimeRecord] = []
    # 每個 NAME_CHTLabel 是一部電影；同一區塊的多個 TIMELabel 都要保留。
    for title_node in soup.select("span[id$='NAME_CHTLabel']"):
        title = title_node.get_text(" ", strip=True)
        if not movie_matches(title, aliases):
            continue
        movie_table = title_node.find_parent("table")
        movie_row = movie_table.find_parent("tr") if movie_table else None
        screen_table = movie_row.find_parent("table") if movie_row else None
        screen_row = screen_table.find_parent("tr") if screen_table else None
        hall_node = screen_row.select_one("span[id$='SCREEN_NAMELabel']") if screen_row else None
        auditorium = hall_node.get_text(" ", strip=True) if hall_node else None
        for time_node in movie_table.select("span[id$='TIMELabel']") if movie_table else []:
            start_time = time_node.get_text(" ", strip=True)
            if not re.fullmatch(r"\d{1,2}:\d{2}", start_time):
                continue
            records.append(
                ShowtimeRecord(
                    location_id=int(row["id"]),
                    show_date=show_date,
                    start_time=start_time.zfill(5),
                    auditorium=auditorium,
                    format=title,
                    language=infer_language(title),
                    booking_url=LUNA_URL,
                    source_url=LUNA_URL,
                    raw_text=f"{auditorium or ''} {title} {start_time}",
                )
            )
    unique_records: dict[tuple[str, str | None, str | None], ShowtimeRecord] = {}
    for record in records:
        unique_records[(record.start_time, record.auditorium, record.format)] = record
    return list(unique_records.values())


def fetch_ilanmovie(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    rows = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '日新戲院 / 宜蘭電影資訊網'
        ORDER BY cl.location_name
        """
    ).fetchall()
    if not rows:
        return []
    location_by_code = {row["source_location_code"]: row for row in rows}
    default_row = location_by_code.get("main", rows[0])
    raw = request_bytes(ILANMOVIE_URL, headers={"Referer": "https://ilanmovie.com/"})
    save_raw("ilanmovie_index", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records: list[ShowtimeRecord] = []
    month, day = (str(int(part)) for part in show_date.split("-")[1:])
    date_prefix = f"{month}/{day}"
    for box in soup.select(".box1"):
        title_node = box.select_one(".box1-body-content-title")
        title_text = title_node.get_text(" ", strip=True) if title_node else ""
        if not movie_matches(title_text, aliases):
            continue
        theater_node = box.select_one(".box1-title-1")
        theater_name = theater_node.get_text(" ", strip=True) if theater_node else ""
        current_location = location_by_code.get("united") if "統一" in theater_name else default_row
        for table_row in box.select("table tr"):
            cells = [cell.get_text(" ", strip=True) for cell in table_row.find_all("td")]
            if len(cells) < 2 or not cells[0].startswith(date_prefix):
                continue
            for start_time in re.findall(r"\d{1,2}:\d{2}", cells[1]):
                records.append(
                    ShowtimeRecord(
                        location_id=int(current_location["id"]),
                        show_date=show_date,
                        start_time=start_time.zfill(5),
                        auditorium=current_location["location_name"],
                        format=title_text,
                        language=infer_language(title_text),
                        booking_url=ILANMOVIE_URL,
                        source_url=ILANMOVIE_URL,
                        raw_text=f"{theater_name} {title_text}",
                    )
                )
    return records


def render_page_html(url: str, wait_ms: int = 4000) -> str:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="zh-TW", timezone_id="Asia/Taipei")
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(wait_ms)
        html_text = page.content()
        browser.close()
    return html_text


def fetch_windlion(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '金獅影城'
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []
    html_text = render_page_html(f"{WINDLION_URL}#anchor", wait_ms=6000)
    save_raw("windlion_movies", html_text, "html")
    lines = text_blocks_from_html(html_text)
    records: list[ShowtimeRecord] = []
    date_label = f"{show_date}(五)" if show_date == "2026-06-26" else show_date
    current_title: str | None = None
    current_language: str | None = None
    in_target_date = False
    for line in lines:
        if movie_matches(line, aliases):
            current_title = line
            current_language = None
            in_target_date = False
            continue
        if current_title and line.startswith("語言"):
            current_language = line.replace("語言", "").replace(":", "").strip()
            continue
        if re.match(r"\d{4}-\d{2}-\d{2}", line):
            in_target_date = line.startswith(show_date)
            continue
        if not current_title or not in_target_date:
            continue
        match = re.search(r"(\d{1,2}:\d{2})\(([^)]+)\)", line)
        if not match:
            continue
        format_text = " ".join(value for value in [current_title, current_language] if value)
        records.append(
            ShowtimeRecord(
                location_id=int(row["id"]),
                show_date=show_date,
                start_time=match.group(1).zfill(5),
                auditorium=match.group(2),
                format=format_text,
                language=infer_language(current_language or current_title),
                booking_url=WINDLION_URL,
                source_url=WINDLION_URL,
                raw_text=format_text,
            )
        )
    return records


def fetch_ptcinema(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    rows = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '中影屏東影城' AND cl.active = 1
        """
    ).fetchall()
    if not rows:
        return []
    records: list[ShowtimeRecord] = []

    for row in rows:
        # 同一個中影品牌的各場館僅網域不同，時刻表與 POP UP 結構相同。
        location_url = row["location_url"] or row["source_url"] or PTCINEMA_URL.format(show_date=show_date)
        parsed_url = urllib.parse.urlsplit(location_url)
        time_path = parsed_url.path.rstrip("/")
        if not time_path.endswith("/time"):
            time_path = f"{time_path}/time" if time_path else "/time"
        source_url = urllib.parse.urlunsplit((parsed_url.scheme, parsed_url.netloc, time_path, f"date={show_date}", ""))
        raw = request_bytes(source_url, headers={"Referer": f"{parsed_url.scheme}://{parsed_url.netloc}/"}, verify_ssl=False)
        save_raw(f"movie_com_tw_time_{row['id']}", raw, "html")
        soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")

        for anchor in soup.select("a.link_lb[href*='lightbox/index']"):
            # 電影名稱在清單卡片的 info_mask；POP UP 明細本身不含片名。
            title_node = anchor.select_one(".info_mask .movie_title")
            title = title_node.get_text(" ", strip=True) if title_node else anchor.get_text(" ", strip=True)
            if not movie_matches(title, aliases):
                continue
            detail_url = urllib.parse.urljoin(source_url, anchor.get("href", ""))
            try:
                detail = request_text(detail_url, headers={"Referer": source_url}, verify_ssl=False)
            except Exception:
                continue
            save_raw(f"movie_com_tw_lightbox_{row['id']}", detail, "html")
            detail_soup = BeautifulSoup(detail, "html.parser")
            booking_node = detail_soup.select_one("a.btn_buy[href]")
            booking_url = booking_node.get("href") if booking_node else source_url

            # 每個 ul.time_list 都是一個日期區塊：第一個 li.time 是日期，其餘 li 是時刻。
            for time_list in detail_soup.select("ul.time_list"):
                date_node = time_list.select_one("li.time")
                if not date_node:
                    continue
                date_match = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})", date_node.get_text(" ", strip=True))
                if not date_match:
                    continue
                month, day = (int(value) for value in date_match.groups())
                if f"{month:02d}-{day:02d}" != show_date[5:]:
                    continue

                for item in time_list.select("li:not(.time)"):
                    for start_time in re.findall(r"\b\d{1,2}:\d{2}\b", item.get_text(" ", strip=True)):
                        records.append(
                            ShowtimeRecord(
                                location_id=int(row["id"]),
                                show_date=show_date,
                                start_time=start_time.zfill(5),
                                auditorium=None,
                                format=title,
                                language=infer_language(title),
                                booking_url=booking_url,
                                source_url=detail_url,
                                raw_text=time_list.get_text(" ", strip=True),
                            )
                        )
    return records


def select_vieshow_location(page, code: str) -> tuple[bool, str]:
    selectors = [
        "#CinemaNameTWInfoF",
        "#CinemaNameTWInfoS",
    ]

    # 1. 先嘗試 Playwright 正常選取目前可見的中文選單
    for selector in selectors:
        locator = page.locator(selector)

        try:
            if locator.count() == 0:
                continue

            info = locator.evaluate(
                """
                (select, code) => ({
                    id: select.id || "",
                    value: select.value || "",
                    visible: !!(select.offsetWidth || select.offsetHeight || select.getClientRects().length),
                    enabled: !select.disabled,
                    hasCode: Array.from(select.options).some(o => (o.value || "").trim() === code),
                    optionCount: select.options.length
                })
                """,
                code,
            )

            if not info["hasCode"]:
                continue

            if info["visible"] and info["enabled"]:
                locator.select_option(code, timeout=8000)
                page.wait_for_timeout(7000)

                selected_value = locator.evaluate("select => select.value")
                return True, f"selected {selector}, selected_value={selected_value}"

        except Exception as exc:
            print(f"[VIESHOW] normal select failed selector={selector} code={code} error={exc}")

    # 2. 如果正常 select 失敗，改用 JS 強制選取所有有該 code 的 select
    try:
        result = page.evaluate(
            """
            async (code) => {
                const selectors = [
                    "#CinemaNameTWInfoF",
                    "#CinemaNameTWInfoS",
                    "#CinemaNameENInfoF",
                    "#CinemaNameENInfoS"
                ];

                const matched = [];

                for (const selector of selectors) {
                    const el = document.querySelector(selector);
                    if (!el) {
                        continue;
                    }

                    const hasCode = Array.from(el.options).some(
                        option => (option.value || "").trim() === code
                    );

                    if (!hasCode) {
                        continue;
                    }

                    el.value = code;

                    el.dispatchEvent(new Event("input", { bubbles: true }));
                    el.dispatchEvent(new Event("change", { bubbles: true }));

                    matched.push({
                        selector,
                        value: el.value,
                        visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                        enabled: !el.disabled
                    });
                }

                return matched;
            }
            """,
            code,
        )

        if not result:
            return False, f"code={code} not found in known VIESHOW selects"

        page.wait_for_timeout(7000)

        return True, f"force selected by JS: {result}"

    except Exception as exc:
        return False, f"force select failed: {exc}"


def fetch_vieshow(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    rows = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name IN ('威秀影城 / VIESHOW', 'MUVIE CINEMAS')
          AND cl.active = 1
          AND cl.source_location_code IS NOT NULL
        ORDER BY cc.chain_name, cl.location_name
        """
    ).fetchall()

    if not rows:
        return []

    records: list[ShowtimeRecord] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
            slow_mo=200,
        )

        context = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
        )

        page = context.new_page()
        page.goto(VIESHOW_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(8000)

        if "Access Denied" in page.content():
            context.close()
            browser.close()
            raise RuntimeError("VIESHOW ShowTimes returned Access Denied in automated browser.")

        for row in rows:
            code = str(row["source_location_code"])
            location_name = row["location_name"]

            print(f"[VIESHOW] selecting {code} | {location_name}")

            ok, message = select_vieshow_location(page, code)
            print(f"[VIESHOW] select ok={ok} | {message}")

            if not ok:
                continue

            html_text = page.content()
            save_raw(f"vieshow_{code}", html_text, "html")

            soup = BeautifulSoup(html_text, "html.parser")

            before_count = len(records)

            for block in html_blocks_with_movie(soup, aliases):
                records.extend(
                    records_from_text_block(
                        location_id=int(row["id"]),
                        show_date=show_date,
                        text=block.get_text("\n", strip=True),
                        aliases=aliases,
                        source_url=VIESHOW_URL,
                        booking_url=VIESHOW_URL,
                    )
                )

            added = len(records) - before_count
            print(f"[VIESHOW] {code} | {location_name} | records={added}")

        context.close()
        browser.close()

    return records


def clear_existing(conn: sqlite3.Connection, movie_id: int, show_date: str) -> None:
    conn.execute(
        "DELETE FROM showtimes WHERE movie_id = ? AND show_date = ?",
        (movie_id, show_date),
    )


def clear_source_showtimes(
    conn: sqlite3.Connection, movie_id: int, show_date: str, source_name: str
) -> None:
    """只清除「此來源」上次為該電影/日期寫入的場次。

    透過 showtimes.crawl_run_id → crawl_runs.source_name 對應到來源。這樣某來源
    失敗時，不會動到它上次成功的資料，也不會誤傷其他來源——只有成功重抓的來源
    會先清掉自己的舊資料再寫入新的。沒抓到的影城自然就沒有場次、地圖上不顯示。
    """
    conn.execute(
        """
        DELETE FROM showtimes
        WHERE movie_id = ?
          AND show_date = ?
          AND crawl_run_id IN (
              SELECT id FROM crawl_runs WHERE source_name = ?
          )
        """,
        (movie_id, show_date, source_name),
    )


def run_source(
    conn: sqlite3.Connection,
    movie_id: int,
    source_name: str,
    source_url: str,
    fetcher,
    aliases: list[str],
    show_date: str,
    keep_existing: bool = False,
) -> tuple[int, int, str | None]:
    run_id = start_run(conn, movie_id, source_name, source_url)
    try:
        records = fetcher(conn, aliases, show_date)
        # 只有成功抓到（未拋例外）才清掉此來源的舊資料，再寫入新資料。
        # 失敗的來源會直接跳到 except，保留其上次的場次不動。
        if not keep_existing:
            clear_source_showtimes(conn, movie_id, show_date, source_name)
        saved = save_showtimes(conn, movie_id, run_id, records)
        finish_run(conn, run_id, "success", len(records), saved)
        conn.commit()
        return len(records), saved, None
    except Exception as exc:
        finish_run(conn, run_id, "failed", 0, 0, str(exc))
        conn.commit()
        return 0, 0, str(exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch today's showtimes for a movie from official cinema sources.")
    parser.add_argument("movie_title", help="Canonical movie title to save in the database.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Show date, defaults to today.")
    parser.add_argument("--alias", action="append", default=[], help="Additional movie title alias. Can be repeated.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--keep-existing", action="store_true", help="完全不刪任何舊場次（各來源都用 upsert 疊加）。")
    parser.add_argument("--wipe-all", action="store_true", help="舊行為：開頭把該電影/日期所有場次全刪再重抓（一次失敗會誤傷好資料，不建議）。預設改為各來源成功時才清自己的舊資料。")
    args = parser.parse_args()

    aliases = [args.movie_title, *args.alias]
    if args.movie_title in {"玩具總動員5", "玩具總動員 5", "Toy Story 5"}:
        aliases.extend(["Toy Story 5", "玩具總動員５", "玩具總動員 5"])
    sources = [
        ("威秀影城 / VIESHOW + MUVIE CINEMAS", VIESHOW_URL, fetch_vieshow),
        ("秀泰影城", SHOWTIMES_BOOTSTRAP_URL, fetch_showtimes_showtimes_api),
        ("國賓影城", "https://www.ambassador.com.tw/home/TheaterList", fetch_ambassador),
        ("新光影城", SKCINEMAS_FILMS_URL, fetch_skcinemas),
        ("in89 豪華影城", "https://www.in89cinemax.com/", fetch_in89),
        ("喜樂時代影城", CENTURYASIA_URL, fetch_centuryasia),
        ("美麗新影城", MIRANEW_TIMETABLE_URL, fetch_miranew),
        ("天台影城", TMOVIES_URL, fetch_tmovies),
        ("哈拉影城", HALAR_URL, fetch_halar),
        ("美麗華影城", MIRAMAR_URL, fetch_miramar),
        ("南台影城", NANTAI_URL, fetch_nantai),
        ("樂聲影城", LUX_URL, fetch_lux),
        ("台鋁影城", MLD_URL, fetch_mld),
        ("鴻金寶麻吉影城", MACHI_URL, fetch_machi),
        ("光點華山電影館", SPOT_HS_URL, fetch_spot_hs),
        ("微風影城", BREEZE_URL, fetch_breeze),
        ("總督數位影城", GOVERNOR_URL, fetch_governor),
        ("誠品電影院", ESLITE_URL, fetch_eslite),
        ("南投戲院", NANTOU_URL.format(show_date=args.date), fetch_nantou),
        ("埔里山明影城", SHANMING_URL, fetch_shanming),
        ("清水時代影城", TIMES_URL, fetch_timescinema),
        ("威尼斯影城", VENICE_URL.format(page=1), fetch_venice),
        ("親親影城 / 親親戲院", CCMOVIE_URL, fetch_ccmovie),
        ("王牌映画影城", ACE_URL, fetch_acecinema),
        ("環球中華影城", UCH_URL, fetch_uch),
        ("百老匯影城", "https://www.broadway-cineplex.com.tw/book.html", fetch_broadway),
        ("高雄環球影城", UMOVIE_URL, fetch_umovie),
        ("中影屏東影城", PTCINEMA_URL.format(show_date=args.date), fetch_ptcinema),
        ("新月豪華影城", LUNA_URL, fetch_luna),
        ("日新戲院 / 宜蘭電影資訊網", ILANMOVIE_URL, fetch_ilanmovie),
        ("金獅影城", WINDLION_URL, fetch_windlion),
    ]

    init_db(args.db)
    with sqlite3.connect(args.db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        movie_id = get_movie_id(conn, args.movie_title)
        if args.wipe_all and not args.keep_existing:
            # 舊行為（可選）：開頭把整個電影/日期全刪，再重抓所有來源。
            clear_existing(conn, movie_id, args.date)
            conn.commit()

        total_found = 0
        total_saved = 0
        failures: list[tuple[str, str]] = []
        for source_name, source_url, fetcher in sources:
            found, saved, error = run_source(
                conn, movie_id, source_name, source_url, fetcher, aliases, args.date,
                keep_existing=args.keep_existing,
            )
            total_found += found
            total_saved += saved
            if error:
                failures.append((source_name, error))
            print(f"{source_name}: found={found} saved={saved}" + (f" error={error}" if error else ""))

        print(f"Movie: {args.movie_title}")
        print(f"Date: {args.date}")
        print(f"Total found: {total_found}")
        print(f"Total saved: {total_saved}")
        if failures:
            print("Failures:")
            for source_name, error in failures:
                print(f"- {source_name}: {error}")


if __name__ == "__main__":
    main()
