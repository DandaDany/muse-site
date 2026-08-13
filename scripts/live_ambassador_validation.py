from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

from fetch_movie_showtimes import (
    TAIPEI,
    ambassador_url,
    fetch_ambassador_location,
    infer_language,
    request_text,
)


DEFAULT_CODE = "453b2966-f7c2-44a9-b2eb-687493855d0e"


def official_groups(item) -> list[dict[str, str | None]]:
    rows = []
    box = item.select_one(".theater-box") or item
    for tag in box.select(":scope > .tag-seat"):
        seat_list = tag.find_next_sibling("ul", class_="seat-list")
        if seat_list is None:
            continue
        raw_format_text = tag.get_text(" ", strip=True)
        version_match = re.match(r"^[（(]\s*([^）)]+?)\s*[）)]", raw_format_text)
        format_text = version_match.group(1).strip() if version_match else raw_format_text
        for time_node in seat_list.select("li h6"):
            start_time = time_node.get_text(" ", strip=True).zfill(5)
            rows.append({"time": start_time, "format": format_text, "language": infer_language(format_text)})
    return sorted(rows, key=lambda row: (row["time"], row["format"] or ""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(TAIPEI).date().isoformat())
    parser.add_argument("--location-code", default=DEFAULT_CODE)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    args.log.parent.mkdir(parents=True, exist_ok=True)

    source_url = ambassador_url(args.location_code, args.date)
    html = request_text(source_url, headers={"Referer": "https://www.ambassador.com.tw/home/TheaterList"})
    (args.artifact_dir / "ambassador-live.html").write_text(html, encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    selected = None
    for item in soup.select(".showtime-item"):
        rows = official_groups(item)
        languages = {row["language"] for row in rows if row["language"]}
        if len(languages) >= 2:
            title_node = item.select_one("h3 a")
            if title_node:
                selected = (item, title_node.get_text(" ", strip=True), rows)
                break
    if selected is None:
        raise RuntimeError("No same-movie multi-language Ambassador fixture found on the live page.")

    _, title, official = selected
    records = fetch_ambassador_location(
        {"id": 1, "source_location_code": args.location_code},
        [title],
        args.date,
    )
    crawler = sorted(
        [{"time": r.start_time, "format": r.format, "language": r.language} for r in records],
        key=lambda row: (row["time"], row["format"] or ""),
    )
    result = {
        "status": "PASS" if crawler == official else "FAIL",
        "date": args.date,
        "movie": title,
        "source_url": source_url,
        "official": official,
        "crawler": crawler,
    }
    args.log.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
