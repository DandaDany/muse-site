from __future__ import annotations

import argparse
import json
import re
import sqlite3
import urllib.request
from datetime import date
from pathlib import Path

from init_db import DEFAULT_DB_PATH, init_db


MIRANEW_CHAIN = {
    "chain_name": "美麗新影城",
    "official_url": "https://www.miranewcinemas.com/",
    "crawl_url": "https://www.miranewcinemas.com/Booking/Timetable",
    "notes": "Booking/Timetable 頁面內嵌 CinemaList，可取得目前下拉選單與場次影院群組。",
}

MIRANEW_LOCATION_METADATA = {
    "1004": {
        "city": "桃園市",
        "address": "桃園市蘆竹區南崁路一段112號7樓",
        "notes": "美麗新台茂影城；地址由官方 AboutUs 台茂頁補齊。",
    },
    "1005": {
        "city": "台北市",
        "address": "台北市中山區北安路780號B2",
        "notes": "美麗新大直皇家影城；地址由官方 AboutUs 皇家頁補齊。",
    },
    "1007": {
        "city": "桃園市",
        "address": "桃園市蘆竹區南崁路一段112號7樓",
        "notes": "美麗新台茂皇家影城；頁尾列示，但未必出現在當前 Timetable 的 CinemaGroup。",
    },
}

FIXED_CHAIN_LOCATIONS = [
    {
        "chain": {
            "chain_name": "天台影城",
            "official_url": "https://www.t-movies.com.tw/",
            "crawl_url": "https://www.t-movies.com.tw/index.php",
            "notes": "單一據點影城，首頁可直接取得場次與影城資訊。",
        },
        "locations": [
            {
                "location_name": "三重天台影城",
                "city": "新北市",
                "address": "新北市三重區重新路二段78號4F(天台廣場)",
                "source_location_code": "main",
                "location_url": "https://www.t-movies.com.tw/index.php",
                "source_url": "https://www.t-movies.com.tw/index.php",
                "notes": "官方首頁頁尾/影城資訊來源。",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "威尼斯影城",
            "official_url": "https://www.venice-cinemas.com.tw/",
            "crawl_url": "https://www.venice-cinemas.com.tw/showtime.php",
            "notes": "單一據點；時刻表支援跨頁查詢。",
        },
        "locations": [
            {
                "location_name": "桃園中壢威尼斯影城",
                "city": "桃園市",
                "address": "桃園市中壢區九和一街48號3樓之2",
                "source_location_code": "main",
                "location_url": "https://www.venice-cinemas.com.tw/showtime.php?movie_date=&page=2",
                "source_url": "https://www.venice-cinemas.com.tw/showtime.php?movie_date=&page=2",
                "notes": "官方時刻表頁尾來源；客服專線 03-280-5018。",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "百老匯影城",
            "official_url": "https://www.broadway-cineplex.com.tw/",
            "crawl_url": "https://www.broadway-cineplex.com.tw/book.html",
            "notes": "兩個據點以 book.html 的 obj 參數區分。",
        },
        "locations": [
            {
                "location_name": "公館百老匯影城",
                "city": "台北市",
                "address": "台北市文山區羅斯福路四段200號",
                "source_location_code": "Taipei",
                "location_url": "https://www.broadway-cineplex.com.tw/book.html?obj=Taipei&v25080101",
                "source_url": "https://www.broadway-cineplex.com.tw/contact.html",
                "notes": "官方聯繫我們頁來源；電話 02-8663-6128。",
            },
            {
                "location_name": "竹北百老匯影城",
                "city": "新竹縣",
                "address": "新竹縣竹北市自強南路36號3~5樓",
                "source_location_code": "Zhubei",
                "location_url": "https://www.broadway-cineplex.com.tw/book.html?obj=Zhubei&v25080101",
                "source_url": "https://www.broadway-cineplex.com.tw/contact.html",
                "notes": "官方聯繫我們頁來源；電話 03-667-6059。",
            },
        ],
    },
    {
        "chain": {
            "chain_name": "親親影城 / 親親戲院",
            "official_url": "https://www.ccmovie.com.tw/",
            "crawl_url": "https://www.ccmovie.com.tw/product.php?_path=product_showtimes",
            "notes": "單一據點；放映場次頁直接列出所有現正熱映場次。",
        },
        "locations": [
            {
                "location_name": "親親影城",
                "city": "台中市",
                "address": "台中市北區北屯路14號",
                "source_location_code": "main",
                "location_url": "https://www.ccmovie.com.tw/product.php?_path=product_showtimes",
                "source_url": "https://www.ccmovie.com.tw/product.php?_path=product_showtimes",
                "notes": "官方放映場次頁來源；電話 04-22319111。",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "王牌映画影城",
            "official_url": "https://www.acecinema.com.tw/",
            "crawl_url": "https://www.acecinema.com.tw/movie/now",
            "notes": "單一據點；現正熱映頁可作為場次/電影入口。",
        },
        "locations": [
            {
                "location_name": "王牌映画影城－廣三SOGO店",
                "city": "台中市",
                "address": "台中市西區臺灣大道二段459號18樓",
                "source_location_code": "main",
                "location_url": "https://www.acecinema.com.tw/movie/now",
                "source_url": "https://www.acecinema.com.tw/movie/now",
                "notes": "官方現正熱映頁 meta 描述列示位於廣三崇光百貨18樓；地址由廣三SOGO位置補齊。",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "環球中華影城",
            "official_url": "https://www.uch-movies.tw/",
            "crawl_url": "https://www.uch-movies.tw/time.aspx",
            "notes": "單一據點；時刻查詢頁有日期選單與場次入口。",
        },
        "locations": [
            {
                "location_name": "斗六環球中華影城",
                "city": "雲林縣",
                "address": "雲林縣斗六市雲林路二段19號",
                "source_location_code": "main",
                "location_url": "https://www.uch-movies.tw/time.aspx",
                "source_url": "https://www.uch-movies.tw/time.aspx",
                "notes": "官方時刻查詢頁頁尾來源；電話 05-5332660。",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "高雄環球影城",
            "official_url": "https://www.u-movie.com.tw/",
            "crawl_url": "https://www.u-movie.com.tw/cinema/page.php?page_type=now&ver=tw&portal=cinema",
            "notes": "單一據點；熱售中頁面直接列出當日場次與訂票連結。",
        },
        "locations": [
            {
                "location_name": "高雄環球影城",
                "city": "高雄市",
                "address": "高雄市苓雅區大順三路108號",
                "source_location_code": "main",
                "location_url": "https://www.u-movie.com.tw/cinema/page.php?page_type=now&ver=tw&portal=cinema",
                "source_url": "https://www.u-movie.com.tw/cinema/page.php?page_type=now&ver=tw&portal=cinema",
                "notes": "官方熱售中頁頁尾來源；電話 07-722-0066。",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "中影屏東影城",
            "official_url": "https://ptcinema.movie.com.tw/",
            "crawl_url": "https://ptcinema.movie.com.tw/time?date={date}",
            "notes": "單一據點；時刻查詢頁以 date 參數指定放映日期，電影細節頁可補場次。",
        },
        "locations": [
            {
                "location_name": "中影屏東影城",
                "city": "屏東縣",
                "address": "屏東縣屏東市民生路248號",
                "source_location_code": "main",
                "location_url": "https://ptcinema.movie.com.tw/time?date={date}",
                "source_url": "https://ptcinema.movie.com.tw/contact",
                "notes": "官方聯絡我們頁來源；電話 08-732-2043。場次需進入作品細節解析。",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "新月豪華影城",
            "official_url": "https://www.lunacinemax.com.tw/",
            "crawl_url": "https://www.lunacinemax.com.tw/time_schedule.aspx",
            "notes": "單一據點；各廳播映場次頁直接列出日期、影廳、片名與時間。",
        },
        "locations": [
            {
                "location_name": "宜蘭新月豪華影城",
                "city": "宜蘭縣",
                "address": "宜蘭縣宜蘭市民權路二段38巷2號",
                "source_location_code": "main",
                "location_url": "https://www.lunacinemax.com.tw/time_schedule.aspx",
                "source_url": "https://www.lunacinemax.com.tw/time_schedule.aspx",
                "notes": "官方各廳播映場次頁來源；地址依蘭城新月廣場影城地址補齊，待官方頁面可解析時再覆核。",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "日新戲院 / 宜蘭電影資訊網",
            "official_url": "https://ilanmovie.com/",
            "crawl_url": "https://ilanmovie.com/index.php",
            "notes": "宜蘭電影資訊網聚合日新戲院場次；本館與統一廳先分成兩個地圖據點。",
        },
        "locations": [
            {
                "location_name": "羅東日新戲院本館",
                "city": "宜蘭縣",
                "address": "宜蘭縣羅東鎮中山西街17之1號",
                "source_location_code": "main",
                "location_url": "https://ilanmovie.com/index.php",
                "source_url": "https://ilanmovie.com/index.php",
                "notes": "宜蘭電影資訊網入口；地址待官方頁面可解析時再覆核。",
            },
            {
                "location_name": "羅東日新戲院統一廳",
                "city": "宜蘭縣",
                "address": "宜蘭縣羅東鎮公園路100號3樓",
                "source_location_code": "united",
                "location_url": "https://ilanmovie.com/index.php",
                "source_url": "https://ilanmovie.com/index.php",
                "notes": "宜蘭電影資訊網入口；地址待官方頁面可解析時再覆核。",
            },
        ],
    },
    {
        "chain": {
            "chain_name": "金獅影城",
            "official_url": "https://cinemax.windlion.com.tw/",
            "crawl_url": "https://cinemax.windlion.com.tw/movies.php#anchor",
            "notes": "單一據點；movies.php 直接列出各電影多日場次。",
        },
        "locations": [
            {
                "location_name": "金門金獅影城",
                "city": "金門縣",
                "address": "金門縣金湖鎮中山路8-8號西棟3F",
                "source_location_code": "main",
                "location_url": "https://cinemax.windlion.com.tw/movies.php#anchor",
                "source_url": "https://cinemax.windlion.com.tw/show.php?id=20",
                "notes": "官方交通指南頁來源；電話 0800-586-388。",
            }
        ],
    },
]


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def extract_miranew_locations(html: str) -> list[dict[str, object]]:
    match = re.search(r"var CinemaList = '(.*?)';\s*CinemaList = CinemaList", html, re.S)
    if not match:
        raise ValueError("找不到美麗新 Timetable 頁面的 CinemaList 變數")

    payload = json.loads(match.group(1).replace('\\"', '"'))
    groups = payload.get("Data", {}).get("CinemaGroup", [])
    locations: list[dict[str, object]] = []
    for group in groups:
        cinema_id = str(group.get("CinemaId") or "").strip()
        name = str(group.get("CinemaCName") or "").strip()
        if not cinema_id or not name:
            continue
        metadata = MIRANEW_LOCATION_METADATA.get(cinema_id, {})
        locations.append(
            {
                "location_name": name,
                "city": metadata.get("city"),
                "address": metadata.get("address"),
                "source_location_code": cinema_id,
                "location_url": MIRANEW_CHAIN["crawl_url"],
                "source_url": MIRANEW_CHAIN["crawl_url"],
                "notes": metadata.get("notes") or "美麗新 Timetable CinemaList.CinemaGroup 來源。",
            }
        )
    return locations


def format_date_values(value: object, show_date: str) -> object:
    if not isinstance(value, str):
        return value
    return value.format(
        date=show_date,
        date_slash=show_date.replace("-", "/"),
        date_compact=show_date.replace("-", ""),
    )


def apply_date_to_group(group: dict[str, object], show_date: str) -> dict[str, object]:
    chain = {
        key: format_date_values(value, show_date)
        for key, value in group["chain"].items()
    }
    locations = [
        {
            key: format_date_values(value, show_date)
            for key, value in location.items()
        }
        for location in group["locations"]
    ]
    return {"chain": chain, "locations": locations}


def upsert_chain(conn: sqlite3.Connection, chain: dict[str, str]) -> int:
    conn.execute(
        """
        INSERT INTO cinema_chains (
            chain_name,
            official_url,
            crawl_url,
            all_locations_assumed_showing,
            notes
        )
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(chain_name) DO UPDATE SET
            official_url = excluded.official_url,
            crawl_url = excluded.crawl_url,
            all_locations_assumed_showing = 1,
            notes = excluded.notes,
            active = 1
        """,
        (chain["chain_name"], chain["official_url"], chain["crawl_url"], chain.get("notes")),
    )
    row = conn.execute("SELECT id FROM cinema_chains WHERE chain_name = ?", (chain["chain_name"],)).fetchone()
    return int(row[0])


def upsert_location(conn: sqlite3.Connection, chain_id: int, location: dict[str, object]) -> None:
    conn.execute(
        """
        INSERT INTO cinema_locations (
            chain_id,
            location_name,
            address,
            city,
            source_location_code,
            location_url,
            source_url,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chain_id, location_name) DO UPDATE SET
            address = COALESCE(excluded.address, cinema_locations.address),
            city = COALESCE(excluded.city, cinema_locations.city),
            source_location_code = excluded.source_location_code,
            location_url = excluded.location_url,
            source_url = excluded.source_url,
            notes = excluded.notes,
            active = 1
        """,
        (
            chain_id,
            location["location_name"],
            location.get("address"),
            location.get("city"),
            location.get("source_location_code"),
            location.get("location_url"),
            location.get("source_url"),
            location.get("notes"),
        ),
    )


def save_locations(miranew_locations: list[dict[str, object]], db_path: Path, show_date: str) -> int:
    init_db(db_path)
    saved = 0
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        miranew_chain_id = upsert_chain(conn, MIRANEW_CHAIN)
        for location in miranew_locations:
            upsert_location(conn, miranew_chain_id, location)
            saved += 1

        for raw_group in FIXED_CHAIN_LOCATIONS:
            group = apply_date_to_group(raw_group, show_date)
            chain_id = upsert_chain(conn, group["chain"])
            for location in group["locations"]:
                upsert_location(conn, chain_id, location)
                saved += 1

    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Miranew and smaller/single-location cinema locations into SQLite."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Show date for date-based cinema URLs.")
    parser.add_argument(
        "--miranew-html",
        type=Path,
        help="Optional local Miranew Booking/Timetable HTML path for offline parsing.",
    )
    args = parser.parse_args()

    if args.miranew_html:
        miranew_html = args.miranew_html.read_text(encoding="utf-8", errors="ignore")
    else:
        miranew_html = fetch_text(MIRANEW_CHAIN["crawl_url"])

    miranew_locations = extract_miranew_locations(miranew_html)
    saved = save_locations(miranew_locations, args.db, args.date)

    print(f"Saved locations: {saved}")
    print("Miranew locations:")
    for location in miranew_locations:
        print(f"{location['source_location_code']} | {location['location_name']}")


if __name__ == "__main__":
    main()
