from __future__ import annotations

import argparse
import ast
import html
import json
import re
import ssl
import sqlite3
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from init_db import DEFAULT_DB_PATH, init_db


PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_DIR / "data" / "output" / "showtimes"
TAIPEI = ZoneInfo("Asia/Taipei")
SHOWTIMES_BOOTSTRAP_URL = "https://capi.showtimes.com.tw/4/app/bootstrap"
VIESHOW_URL = "https://www.vscinemas.com.tw/ShowTimes/"
SKCINEMAS_FILMS_URL = "https://www.skcinemas.com/films"
SKCINEMAS_SESSION_API = "https://www.skcinemas.com/api/VistaDataV2/GetSessionByCinemasIDForApp"
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
    return re.sub(r"[\s　:：,，.。()（）\[\]【】\-–—_．・‧|｜]+", "", value)


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


def capture_skcinemas_headers(entry_url: str) -> dict[str, str]:
    captured: dict[str, str] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="zh-TW", timezone_id="Asia/Taipei")

        def on_request(request) -> None:
            nonlocal captured
            if captured or "/api/VistaDataV2/" not in request.url:
                return
            headers = request.headers
            required = ["timestamp", "did", "token"]
            if all(headers.get(key) for key in required):
                captured = {
                    "timestamp": headers["timestamp"],
                    "DID": headers["did"],
                    "token": headers["token"],
                    "Referer": entry_url,
                }

        page.on("request", on_request)
        page.goto(entry_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(7000)
        browser.close()

    if not captured:
        raise RuntimeError("Could not capture Shin Kong Cinemas API headers.")
    return captured


def fetch_skcinemas(conn: sqlite3.Connection, aliases: list[str], show_date: str) -> list[ShowtimeRecord]:
    rows = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '新光影城'
          AND cl.active = 1
          AND cl.source_location_code IS NOT NULL
        ORDER BY cl.location_name
        """
    ).fetchall()
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
            continue
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
    dt = urllib.parse.quote(show_date.replace("-", "/"), safe="")
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
                    booking_url=None,
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
    lines = text_blocks_from_html(raw)
    records: list[ShowtimeRecord] = []
    current_hall: str | None = None
    for index, line in enumerate(lines):
        if re.fullmatch(r"(VIP|\d+廳)", line):
            current_hall = line
            continue
        if not movie_matches(line, aliases):
            continue
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        for start_time in re.findall(r"\d{1,2}:\d{2}", next_line):
            records.append(
                ShowtimeRecord(
                    location_id=int(row["id"]),
                    show_date=show_date,
                    start_time=start_time.zfill(5),
                    auditorium=current_hall,
                    format=line,
                    language=infer_language(line),
                    booking_url=LUNA_URL,
                    source_url=LUNA_URL,
                    raw_text=f"{current_hall or ''} {line}",
                )
            )
    return records


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
    row = conn.execute(
        """
        SELECT cl.*
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        WHERE cc.chain_name = '中影屏東影城'
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return []
    source_url = PTCINEMA_URL.format(show_date=show_date)
    raw = request_bytes(source_url, headers={"Referer": "https://ptcinema.movie.com.tw/"}, verify_ssl=False)
    save_raw("ptcinema_time", raw, "html")
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records: list[ShowtimeRecord] = []

    for option in soup.select("select option"):
        title = option.get_text(" ", strip=True)
        if movie_matches(title, aliases):
            value = option.get("value")
            if value:
                detail_url = f"https://ptcinema.movie.com.tw/lightbox/index?id={value}"
                try:
                    detail = request_text(detail_url, headers={"Referer": source_url}, verify_ssl=False)
                except Exception:
                    continue
                save_raw(f"ptcinema_lightbox_{value}", detail, "html")
                records.extend(
                    records_from_text_block(
                        location_id=int(row["id"]),
                        show_date=show_date,
                        text=BeautifulSoup(detail, "html.parser").get_text("\n", strip=True),
                        aliases=aliases,
                        source_url=detail_url,
                        booking_url=source_url,
                        format_text=title,
                    )
                )

    for anchor in soup.select("a.link_lb[href*='lightbox/index']"):
        anchor_text = anchor.get_text(" ", strip=True)
        if not movie_matches(anchor_text, aliases):
            continue
        detail_url = urllib.parse.urljoin(source_url, anchor.get("href", ""))
        try:
            detail = request_text(detail_url, headers={"Referer": source_url}, verify_ssl=False)
        except Exception:
            continue
        save_raw("ptcinema_lightbox", detail, "html")
        records.extend(
            records_from_text_block(
                location_id=int(row["id"]),
                show_date=show_date,
                text=BeautifulSoup(detail, "html.parser").get_text("\n", strip=True),
                aliases=aliases,
                source_url=detail_url,
                booking_url=source_url,
                format_text=anchor_text,
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


def run_source(
    conn: sqlite3.Connection,
    movie_id: int,
    source_name: str,
    source_url: str,
    fetcher,
    aliases: list[str],
    show_date: str,
) -> tuple[int, int, str | None]:
    run_id = start_run(conn, movie_id, source_name, source_url)
    try:
        records = fetcher(conn, aliases, show_date)
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
    parser.add_argument("--keep-existing", action="store_true", help="Do not delete existing showtimes for this movie/date before saving.")
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
        if not args.keep_existing:
            clear_existing(conn, movie_id, args.date)
        conn.commit()

        total_found = 0
        total_saved = 0
        failures: list[tuple[str, str]] = []
        for source_name, source_url, fetcher in sources:
            found, saved, error = run_source(conn, movie_id, source_name, source_url, fetcher, aliases, args.date)
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
