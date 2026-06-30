from __future__ import annotations

import argparse
import html
import re
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

from init_db import DEFAULT_DB_PATH, init_db


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "data" / "output" / "kml"
KML_NS = "http://www.opengis.net/kml/2.2"


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("_")
    return cleaned or "movie_map"


def value_text(value: object) -> str:
    return "" if value is None else str(value)


def html_link(url: str | None, label: str) -> str:
    if not url:
        return ""
    escaped_url = html.escape(url, quote=True)
    escaped_label = html.escape(label)
    return f'<a href="{escaped_url}">{escaped_label}</a>'


def add_text(parent: ET.Element, tag: str, text: object | None) -> ET.Element:
    child = ET.SubElement(parent, tag)
    child.text = value_text(text)
    return child


def add_extended_data(parent: ET.Element, values: dict[str, object]) -> None:
    extended = ET.SubElement(parent, "ExtendedData")
    for key, value in values.items():
        if value in {None, ""}:
            continue
        data = ET.SubElement(extended, "Data", {"name": key})
        add_text(data, "value", value)


def add_geometry(parent: ET.Element, row: sqlite3.Row) -> bool:
    address = row["address"]
    latitude = row["latitude"]
    longitude = row["longitude"]

    if address:
        add_text(parent, "address", address)

    if latitude is not None and longitude is not None:
        point = ET.SubElement(parent, "Point")
        add_text(point, "coordinates", f"{longitude},{latitude},0")
        return True

    return bool(address)


def location_description(row: sqlite3.Row) -> str:
    links = [
        html_link(row["location_url"], "場次/影城入口"),
        html_link(row["official_url"], "官方網站"),
    ]
    links_text = " ｜ ".join(link for link in links if link)
    parts = [
        f"<b>{html.escape(row['map_name'])}</b>",
        f"品牌：{html.escape(row['chain_name'])}",
        f"影城：{html.escape(row['location_name'])}",
    ]
    if row["address"]:
        parts.append(f"地址：{html.escape(row['address'])}")
    if links_text:
        parts.append(links_text)
    return "<br/>".join(parts)


def showtime_line(row: sqlite3.Row) -> str:
    tags = [
        row["auditorium"],
        row["format"],
        row["language"],
        row["subtitle"],
    ]
    tag_text = " / ".join(value_text(tag) for tag in tags if tag)
    time_text = value_text(row["start_time"])
    if row["end_time"]:
        time_text = f"{time_text}-{row['end_time']}"
    if tag_text:
        time_text = f"{time_text} ({html.escape(tag_text)})"
    if row["booking_url"]:
        return f"{html_link(row['booking_url'], html.escape(time_text))}"
    return html.escape(time_text)


def showtime_description(rows: list[sqlite3.Row]) -> str:
    first = rows[0]
    links = [
        html_link(first["source_url"], "來源頁"),
        html_link(first["booking_url"], "訂票連結") if len(rows) == 1 else "",
    ]
    links_text = " ｜ ".join(link for link in links if link)
    showtimes = "、".join(showtime_line(row) for row in rows)
    parts = [
        f"<b>{html.escape(first['movie_title'])}</b>",
        f"影城：{html.escape(first['map_name'])}",
        f"日期：{html.escape(first['show_date'])}",
        f"場次：{showtimes}",
    ]
    if first["address"]:
        parts.append(f"地址：{html.escape(first['address'])}")
    if links_text:
        parts.append(links_text)
    return "<br/>".join(parts)


def fetch_location_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM v_location_map_points
        ORDER BY chain_name, location_name
        """
    ).fetchall()


def fetch_showtime_rows(conn: sqlite3.Connection, movie_title: str, show_date: str) -> tuple[int | None, list[sqlite3.Row]]:
    movie_row = conn.execute(
        """
        SELECT id
        FROM movies
        WHERE title = ?
          AND active = 1
        ORDER BY release_date DESC, id DESC
        LIMIT 1
        """,
        (movie_title,),
    ).fetchone()
    if not movie_row:
        return None, []

    rows = conn.execute(
        """
        SELECT *
        FROM v_showtime_map_points
        WHERE movie_title = ?
          AND show_date = ?
        ORDER BY chain_name, location_name, start_time
        """,
        (movie_title, show_date),
    ).fetchall()
    return int(movie_row["id"]), rows


def build_location_kml(rows: list[sqlite3.Row], document_name: str) -> tuple[ET.ElementTree, int, int]:
    root = ET.Element("kml", {"xmlns": KML_NS})
    document = ET.SubElement(root, "Document")
    add_text(document, "name", document_name)

    placemark_count = 0
    skipped_count = 0
    for row in rows:
        if not row["address"] and (row["latitude"] is None or row["longitude"] is None):
            skipped_count += 1
            continue
        placemark = ET.SubElement(document, "Placemark")
        add_text(placemark, "name", row["map_name"])
        add_text(placemark, "description", location_description(row))
        add_extended_data(
            placemark,
            {
                "location_id": row["location_id"],
                "chain_name": row["chain_name"],
                "location_name": row["location_name"],
                "address": row["address"],
                "city": row["city"],
                "location_url": row["location_url"],
                "official_url": row["official_url"],
            },
        )
        add_geometry(placemark, row)
        placemark_count += 1

    return ET.ElementTree(root), placemark_count, skipped_count


def build_showtime_kml(rows: list[sqlite3.Row], document_name: str) -> tuple[ET.ElementTree, int, int]:
    root = ET.Element("kml", {"xmlns": KML_NS})
    document = ET.SubElement(root, "Document")
    add_text(document, "name", document_name)

    grouped: dict[tuple[object, ...], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        key = (
            row["chain_name"],
            row["location_name"],
            row["map_name"],
            row["address"],
            row["latitude"],
            row["longitude"],
        )
        grouped[key].append(row)

    placemark_count = 0
    skipped_count = 0
    for group_rows in grouped.values():
        first = group_rows[0]
        if not first["address"] and (first["latitude"] is None or first["longitude"] is None):
            skipped_count += 1
            continue
        placemark = ET.SubElement(document, "Placemark")
        add_text(placemark, "name", first["map_name"])
        add_text(placemark, "description", showtime_description(group_rows))
        add_extended_data(
            placemark,
            {
                "movie_title": first["movie_title"],
                "show_date": first["show_date"],
                "chain_name": first["chain_name"],
                "location_name": first["location_name"],
                "address": first["address"],
                "showtime_count": len(group_rows),
                "start_times": ", ".join(value_text(row["start_time"]) for row in group_rows),
                "source_url": first["source_url"],
            },
        )
        add_geometry(placemark, first)
        placemark_count += 1

    return ET.ElementTree(root), placemark_count, skipped_count


def default_output_path(movie_title: str | None, show_date: str) -> Path:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prefix = safe_filename(movie_title) if movie_title else "locations"
    return DEFAULT_OUTPUT_DIR / f"{prefix}_{show_date}.kml"


def save_export_record(db_path: Path, movie_id: int | None, export_date: str, output_path: Path, placemark_count: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO kml_exports (movie_id, export_date, file_path, placemark_count)
            VALUES (?, ?, ?, ?)
            """,
            (movie_id, export_date, str(output_path), placemark_count),
        )


def write_kml(tree: ET.ElementTree, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export cinema locations or movie showtimes to KML for Google My Maps.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Show date for showtime export.")
    parser.add_argument("--movie-title", help="Exact movie title to export from showtimes. Omit to export all locations.")
    parser.add_argument("--output", type=Path, help="Output KML path.")
    args = parser.parse_args()

    init_db(args.db)
    with sqlite3.connect(args.db) as conn:
        conn.row_factory = sqlite3.Row
        if args.movie_title:
            movie_id, rows = fetch_showtime_rows(conn, args.movie_title, args.date)
            if not rows:
                raise SystemExit(f"No showtimes found for movie={args.movie_title!r} date={args.date}")
            document_name = f"{args.movie_title} 今日場次 {args.date}"
            tree, placemark_count, skipped_count = build_showtime_kml(rows, document_name)
        else:
            movie_id = None
            rows = fetch_location_rows(conn)
            document_name = f"電影上映地圖據點 {args.date}"
            tree, placemark_count, skipped_count = build_location_kml(rows, document_name)

    output_path = args.output or default_output_path(args.movie_title, args.date)
    write_kml(tree, output_path)
    save_export_record(args.db, movie_id, args.date, output_path, placemark_count)

    print(f"KML exported: {output_path}")
    print(f"Placemarks: {placemark_count}")
    print(f"Skipped without address/coordinates: {skipped_count}")


if __name__ == "__main__":
    main()
