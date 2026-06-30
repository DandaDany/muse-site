from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from init_db import DEFAULT_DB_PATH, init_db


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "data" / "output"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
ARCGIS_URL = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
USER_AGENT = "movie-map-kml-geocoder/1.0 (local research script)"

ADDRESS_OVERRIDES = {
    "MUVIE CINEMAS 台中TIGER CITY": "台中市西屯區河南路三段120-1號4樓",
    "MUVIE CINEMAS 台中TIGER CITY (GC)": "台中市西屯區河南路三段120-1號4樓",
    "MUVIE CINEMAS 台北松仁": "台北市信義區松仁路58號10樓",
    "MUVIE CINEMAS 台北松仁 (MUCROWN)": "台北市信義區松仁路58號10樓",
    "中和環球威秀影城": "新北市中和區中山路三段122號4樓",
    "台中iFG 遠雄廣場威秀影城": "台中市東區復興路四段186號4樓",
    "台中大遠百威秀影城": "台中市西屯區台灣大道三段251號13樓",
    "台北京站威秀影城": "台北市大同區市民大道一段209號5樓",
    "台北信義威秀影城": "台北市信義區松壽路20號2樓",
    "台北南港 LaLaport威秀影城": "台北市南港區經貿二路131號5樓",
    "台北西門威秀影城": "台北市萬華區漢中街52號7樓",
    "台南FOCUS威秀影城": "台南市中西區中山路166號11樓",
    "台南南紡威秀影城": "台南市東區中華東路一段366號5樓",
    "台南南紡威秀影城 (GC)": "台南市東區中華東路一段366號5樓",
    "台南大遠百威秀影城": "台南市中西區公園路60號5樓",
    "新店裕隆城威秀影城": "新北市新店區中興路三段128號7樓",
    "新竹大遠百威秀影城": "新竹市東區西大路323號8樓",
    "新竹大遠百威秀影城 (GC)": "新竹市東區西大路323號8樓",
    "新竹巨城威秀影城": "新竹市東區民權路176號4樓",
    "板橋大遠百威秀影城": "新北市板橋區新站路28號10樓",
    "林口MITSUI OUTLET PARK威秀影城": "新北市林口區文化三路一段356號3樓",
    "桃園桃知道威秀影城": "桃園市桃園區南平路301號4樓",
    "桃園統領威秀影城": "桃園市桃園區中正路61號9樓",
    "花蓮新天堂樂園威秀影城": "花蓮縣吉安鄉南濱路一段503號3樓",
    "頭份尚順威秀影城": "苗栗縣頭份市中央路105號7樓",
    "高雄大遠百威秀影城": "高雄市苓雅區三多四路21號13樓",
    "高雄大遠百威秀影城 (GC)": "高雄市苓雅區三多四路21號13樓",
    "台中豐原 in89豪華影城": "台中市豐原區成功路500號5樓",
    "台北西門 in89豪華影城": "台北市萬華區武昌街二段89號",
    "嘉義影食匯 in89豪華影城": "嘉義市東區民族路328號",
    "桃園站前 in89豪華影城": "桃園市桃園區中正路56號",
    "澎湖昇恆昌 in89豪華影城": "澎湖縣馬公市同和路158號4樓",
    "高雄大立 in89豪華影城": "高雄市前金區五福三路57號9樓",
    "高雄鹽埕 in89駁二電影院": "高雄市鹽埕區大勇路5之1號",
    "金門昇恆昌國賓影城": "金門縣金湖鎮太湖路二段198號6樓",
}

CITY_PREFIXES = [
    "台北市",
    "新北市",
    "桃園市",
    "台中市",
    "台南市",
    "高雄市",
    "基隆市",
    "新竹市",
    "嘉義市",
    "苗栗縣",
    "屏東縣",
    "宜蘭縣",
    "花蓮縣",
    "雲林縣",
    "澎湖縣",
    "金門縣",
]


def clean_location_name(name: str) -> str:
    return (
        name.replace("(GC)", "")
        .replace("(MUCROWN)", "")
        .replace("－", " ")
        .replace("_", " ")
        .strip()
    )


def unique_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = " ".join(value.split())
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def city_from_address(address: str | None) -> str | None:
    if not address:
        return None
    for city in CITY_PREFIXES:
        if address.startswith(city):
            return city
    return None


def build_queries(row: sqlite3.Row) -> list[str]:
    chain_name = row["chain_name"] or ""
    location_name = clean_location_name(row["location_name"] or "")
    address = row["address"] or ""
    city = row["city"] or ""

    queries = []
    if address:
        queries.extend([address, f"{address} 台灣"])
    queries.extend(
        [
            f"{location_name} {city} 台灣",
            f"{chain_name} {location_name} {city} 台灣",
            f"{location_name} 台灣",
        ]
    )
    return unique_values(queries)


def fetch_nominatim_geocode(query: str) -> dict[str, object] | None:
    params = urllib.parse.urlencode(
        {
            "format": "jsonv2",
            "q": query,
            "countrycodes": "tw",
            "limit": 1,
            "addressdetails": 1,
            "accept-language": "zh-TW",
        }
    )
    request = urllib.request.Request(
        f"{NOMINATIM_URL}?{params}",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload:
        return None
    match = payload[0]
    return {
        "provider": "nominatim",
        "latitude": match.get("lat"),
        "longitude": match.get("lon"),
        "display_name": match.get("display_name"),
        "score": match.get("importance"),
        "type": match.get("osm_type"),
        "id": match.get("osm_id"),
    }


def fetch_arcgis_geocode(query: str) -> dict[str, object] | None:
    params = urllib.parse.urlencode(
        {
            "SingleLine": query,
            "f": "json",
            "outFields": "Match_addr,Addr_type",
            "maxLocations": 1,
            "sourceCountry": "TWN",
            "langCode": "zh-TW",
        }
    )
    request = urllib.request.Request(
        f"{ARCGIS_URL}?{params}",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    candidates = payload.get("candidates") or []
    if not candidates:
        return None
    match = candidates[0]
    location = match.get("location") or {}
    return {
        "provider": "arcgis",
        "latitude": location.get("y"),
        "longitude": location.get("x"),
        "display_name": match.get("address"),
        "score": match.get("score"),
        "type": (match.get("attributes") or {}).get("Addr_type"),
        "id": None,
    }


def fetch_geocode(query: str) -> dict[str, object] | None:
    for fetcher in [fetch_arcgis_geocode, fetch_nominatim_geocode]:
        match = fetcher(query)
        if not match:
            continue
        score = parse_float(match.get("score"))
        if match.get("provider") == "arcgis" and score is not None and score < 80:
            continue
        return match
    return None


def parse_float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def is_taiwan_coordinate(latitude: float | None, longitude: float | None) -> bool:
    if latitude is None or longitude is None:
        return False
    return 21.5 <= latitude <= 26.5 and 118.0 <= longitude <= 123.8


def rows_to_geocode(conn: sqlite3.Connection, only_missing: bool) -> list[sqlite3.Row]:
    where = "WHERE cl.active = 1 AND cc.active = 1"
    if only_missing:
        where += " AND (cl.latitude IS NULL OR cl.longitude IS NULL)"
    return conn.execute(
        f"""
        SELECT
            cl.id AS location_id,
            cc.chain_name,
            cl.location_name,
            cl.address,
            cl.city,
            cl.latitude,
            cl.longitude
        FROM cinema_locations cl
        JOIN cinema_chains cc ON cc.id = cl.chain_id
        {where}
        ORDER BY cc.chain_name, cl.location_name
        """
    ).fetchall()


def apply_address_overrides(conn: sqlite3.Connection) -> int:
    updated = 0
    for location_name, address in ADDRESS_OVERRIDES.items():
        city = city_from_address(address)
        cursor = conn.execute(
            """
            UPDATE cinema_locations
            SET address = COALESCE(NULLIF(address, ''), ?),
                city = COALESCE(NULLIF(city, ''), ?)
            WHERE location_name = ?
              AND (address IS NULL OR address = '')
            """,
            (address, city, location_name),
        )
        updated += cursor.rowcount
    return updated


def update_location(conn: sqlite3.Connection, location_id: int, latitude: float, longitude: float) -> None:
    conn.execute(
        """
        UPDATE cinema_locations
        SET latitude = ?,
            longitude = ?
        WHERE id = ?
        """,
        (latitude, longitude, location_id),
    )


def output_path_for(path: Path | None) -> Path:
    if path:
        return path
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_OUTPUT_DIR / f"geocode_results_{date.today().isoformat()}.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill missing latitude/longitude values using Nominatim geocoding.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--output", type=Path, help="CSV path for geocoding results.")
    parser.add_argument("--delay", type=float, default=1.1, help="Seconds to wait between Nominatim requests.")
    parser.add_argument("--limit", type=int, help="Limit number of locations to process.")
    parser.add_argument("--all", action="store_true", help="Geocode all active locations, not only missing coordinates.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write coordinates to the database.")
    parser.add_argument(
        "--skip-address-overrides",
        action="store_true",
        help="Do not fill known missing addresses before geocoding.",
    )
    args = parser.parse_args()

    init_db(args.db)
    output_path = output_path_for(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(args.db) as conn, output_path.open("w", newline="", encoding="utf-8") as handle:
        conn.row_factory = sqlite3.Row
        overrides = 0
        if not args.skip_address_overrides and not args.dry_run:
            overrides = apply_address_overrides(conn)
            conn.commit()
            print(f"Address overrides applied: {overrides}", flush=True)

        rows = rows_to_geocode(conn, only_missing=not args.all)
        if args.limit:
            rows = rows[: args.limit]

        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "location_id",
                "chain_name",
                "location_name",
                "provider",
                "query",
                "status",
                "latitude",
                "longitude",
                "display_name",
                "importance",
                "osm_type",
                "osm_id",
            ],
        )
        writer.writeheader()

        saved = 0
        failed = 0
        for index, row in enumerate(rows, start=1):
            print(f"[{index}/{len(rows)}] {row['chain_name']} | {row['location_name']}", flush=True)
            match = None
            matched_query = ""
            for query in build_queries(row):
                try:
                    match = fetch_geocode(query)
                except Exception as exc:  # noqa: BLE001
                    writer.writerow(
                        {
                            "location_id": row["location_id"],
                            "chain_name": row["chain_name"],
                            "location_name": row["location_name"],
                            "provider": "",
                            "query": query,
                            "status": f"error: {exc}",
                        }
                    )
                    time.sleep(args.delay)
                    continue

                time.sleep(args.delay)
                if not match:
                    writer.writerow(
                        {
                            "location_id": row["location_id"],
                            "chain_name": row["chain_name"],
                            "location_name": row["location_name"],
                            "provider": "",
                            "query": query,
                            "status": "not_found",
                        }
                    )
                    continue

                latitude = parse_float(match.get("latitude"))
                longitude = parse_float(match.get("longitude"))
                if not is_taiwan_coordinate(latitude, longitude):
                    writer.writerow(
                        {
                            "location_id": row["location_id"],
                            "chain_name": row["chain_name"],
                            "location_name": row["location_name"],
                            "provider": match.get("provider"),
                            "query": query,
                            "status": "outside_taiwan",
                            "latitude": latitude,
                            "longitude": longitude,
                            "display_name": match.get("display_name"),
                            "importance": match.get("score"),
                            "osm_type": match.get("type"),
                            "osm_id": match.get("id"),
                        }
                    )
                    continue

                matched_query = query
                break

            if not match:
                failed += 1
                continue

            latitude = parse_float(match.get("latitude"))
            longitude = parse_float(match.get("longitude"))
            if not is_taiwan_coordinate(latitude, longitude):
                failed += 1
                continue

            if not args.dry_run:
                update_location(conn, int(row["location_id"]), latitude, longitude)
            saved += 1
            writer.writerow(
                {
                    "location_id": row["location_id"],
                    "chain_name": row["chain_name"],
                    "location_name": row["location_name"],
                    "provider": match.get("provider"),
                    "query": matched_query,
                    "status": "saved" if not args.dry_run else "dry_run",
                    "latitude": latitude,
                    "longitude": longitude,
                    "display_name": match.get("display_name"),
                    "importance": match.get("score"),
                    "osm_type": match.get("type"),
                    "osm_id": match.get("id"),
                }
            )

        if not args.dry_run:
            conn.commit()

    print(f"Geocoding results: {output_path}")
    print(f"Saved: {saved}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()
