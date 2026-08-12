from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "multiday_locations.geojson"
FIXED_NOW_MS = 1786519200000  # 2026-08-12 15:20:00 Asia/Taipei


def install_fixture(page: Page) -> None:
    fixture = FIXTURE.read_text(encoding="utf-8")
    page.route(
        "**/data/locations.geojson",
        lambda route: route.fulfill(status=200, content_type="application/geo+json", body=fixture),
    )
    page.add_init_script(
        f"""
        (() => {{
          const fixedNow = {FIXED_NOW_MS};
          const NativeDate = Date;
          class FixedDate extends NativeDate {{
            constructor(...args) {{ super(...(args.length ? args : [fixedNow])); }}
            static now() {{ return fixedNow; }}
          }}
          FixedDate.parse = NativeDate.parse;
          FixedDate.UTC = NativeDate.UTC;
          window.Date = FixedDate;
        }})()
        """,
    )


def marker_count(page: Page) -> int:
    return page.locator(".cinema-marker").count()


def chip_texts(page: Page) -> list[str]:
    return page.locator("#dateChips .date-chip").all_text_contents()


def center(page: Page) -> dict[str, float]:
    return page.evaluate("() => { const c = map.getCenter(); return {lat: c.lat, lng: c.lng, zoom: map.getZoom()}; }")


def center_is_same(a: dict[str, float], b: dict[str, float]) -> bool:
    return abs(a["lat"] - b["lat"]) < 1e-7 and abs(a["lng"] - b["lng"]) < 1e-7 and a["zoom"] == b["zoom"]


def click_filter(page: Page, container: str, label: str) -> None:
    page.locator(f"{container} .filter-option", has_text=label).click()


def run_desktop(page: Page, report: dict) -> None:
    checks = report["desktop"]
    page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
    page.locator("#summaryText").filter(has_text="電影 A").wait_for()

    checks["date_chips"] = chip_texts(page) == ["今天 8/12", "明天 8/13", "五 8/14"]
    checks["today_auto_now"] = page.locator("#timeFilterCaption").inner_text() == "15:20 後"
    checks["today_markers_and_badges"] = marker_count(page) == 3 and sorted(
        int(value) for value in page.locator(".cinema-showtime-count").all_text_contents()
    ) == [1, 1, 2]

    map_before = center(page)
    page.get_by_role("button", name="明天 8/13").click()
    page.wait_for_timeout(150)
    checks["date_switch_markers_badges"] = marker_count(page) == 2 and sorted(
        int(value) for value in page.locator(".cinema-showtime-count").all_text_contents()
    ) == [2, 3]
    checks["future_all_day"] = (
        page.locator("#timeFilterCaption").inner_text() == "全天"
        and page.locator("#timeSliderKnob").inner_text() == "00:00"
    )
    checks["no_map_jump"] = center_is_same(map_before, center(page))

    page.locator("#mSearchInput").fill("高雄")
    checks["search_sync"] = (
        marker_count(page) == 1
        and page.locator("#mSearchSuggestions .suggestion-row").count() == 1
        and "3 場" in page.locator("#mSearchSuggestions .suggestion-row").inner_text()
    )
    page.locator("#mSearchClear").click()

    click_filter(page, "#cityFilterList", "臺北市")
    checks["city_filter_sync"] = marker_count(page) == 1
    click_filter(page, "#cityFilterList", "臺北市")
    click_filter(page, "#chainFilterList", "測試影城")
    checks["chain_filter_sync"] = marker_count(page) == 1
    click_filter(page, "#chainFilterList", "測試影城")

    page.get_by_role("button", name="今天 8/12").click()
    page.locator(".cinema-marker").first.click()
    page.locator(".leaflet-popup").wait_for()
    page.get_by_role("button", name="明天 8/13").click()
    checks["popup_refresh"] = (
        page.locator(".leaflet-popup").count() == 1
        and "明天 8/13" in page.locator(".leaflet-popup").inner_text()
        and "09:00" in page.locator(".leaflet-popup").inner_text()
    )
    page.get_by_role("button", name="五 8/14").click()
    checks["popup_closes_when_missing"] = page.locator(".leaflet-popup").count() == 0

    page.get_by_role("button", name="明天 8/13").click()
    slider = page.locator("#timeSlider .m-track").bounding_box()
    assert slider
    page.mouse.click(slider["x"] + slider["width"] * 0.75, slider["y"] + slider["height"] / 2)
    checks["future_manual_time"] = (
        page.locator("#timeFilterCaption").inner_text() == "18:00 起"
        and "1 影城上映中，共 2 場次" in page.locator("#summaryText").inner_text()
    )
    page.get_by_role("button", name="今天 8/12").click()
    checks["return_today_auto"] = (
        page.locator("#timeFilterCaption").inner_text() == "15:20 後"
        and "3 影城上映中，共 4 場次" in page.locator("#summaryText").inner_text()
    )

    page.get_by_role("button", name="五 8/14").click()
    page.locator("#movieSelect").select_option(label="電影 B (0)")
    checks["movie_a_814_to_b_812"] = (
        chip_texts(page) == ["今天 8/12", "六 8/15"]
        and page.locator("#dateChips .is-selected").inner_text() == "今天 8/12"
    )
    checks["movie_b_excludes_a_dates"] = "8/13" not in " ".join(chip_texts(page)) and "8/14" not in " ".join(chip_texts(page))
    page.get_by_role("button", name="六 8/15").click()
    checks["movie_b_815"] = marker_count(page) == 2
    page.locator("#movieSelect").select_option(label="電影 A (0)")
    page.locator("#movieSelect").select_option(label="電影 B (2)")
    checks["movie_a_812_to_b_preserved"] = page.locator("#dateChips .is-selected").inner_text() == "今天 8/12"

    page.screenshot(path=str(REPO / "artifacts" / "desktop.png"), full_page=True)


def run_mobile(page: Page, report: dict) -> None:
    checks = report["mobile"]
    page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
    page.locator("#summaryText").filter(has_text="電影 A").wait_for()

    overflow = page.locator("#dateChips").evaluate("el => getComputedStyle(el).overflowX")
    checks["chips_horizontal_scroll"] = overflow == "auto"
    checks["no_horizontal_overflow"] = page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
    tab_boxes = [page.locator(f"#mSeg button:nth-child({index})").bounding_box() for index in range(1, 5)]
    checks["tabs_not_compressed"] = all(box and box["width"] >= 80 for box in tab_boxes)

    page.locator(".cinema-marker").first.click()
    page.locator("#mSheet[aria-hidden='false']").wait_for()
    selected = page.locator(".cinema-marker.is-mobile-selected")
    checks["marker_opens_bottom_sheet"] = selected.count() == 1 and "今天 8/12" in page.locator("#mSheetBody").inner_text()

    page.get_by_role("button", name="明天 8/13").click()
    checks["bottom_sheet_date_refresh"] = (
        page.locator("#mSheet[aria-hidden='false']").count() == 1
        and "明天 8/13" in page.locator("#mSheetBody").inner_text()
        and "09:00" in page.locator("#mSheetBody").inner_text()
    )
    checks["selected_marker_preserved"] = page.locator(".cinema-marker.is-mobile-selected").count() == 1
    checks["sheet_no_overflow"] = page.locator("#mSheetBody").evaluate("el => el.scrollWidth <= el.clientWidth")

    page.screenshot(path=str(REPO / "artifacts" / "mobile.png"), full_page=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=REPO / "artifacts" / "browser-report.json")
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report: dict = {"desktop": {}, "mobile": {}, "errors": []}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            desktop = browser.new_context(viewport={"width": 1440, "height": 1000}, timezone_id="Asia/Taipei")
            page = desktop.new_page()
            install_fixture(page)
            try:
                run_desktop(page, report)
            except Exception:
                report["errors"].append({"suite": "desktop", "traceback": traceback.format_exc()})
                page.screenshot(path=str(REPO / "artifacts" / "desktop-failure.png"), full_page=True)
            finally:
                desktop.close()

            mobile = browser.new_context(viewport={"width": 390, "height": 844}, timezone_id="Asia/Taipei", is_mobile=True, has_touch=True)
            page = mobile.new_page()
            install_fixture(page)
            try:
                run_mobile(page, report)
            except Exception:
                report["errors"].append({"suite": "mobile", "traceback": traceback.format_exc()})
                page.screenshot(path=str(REPO / "artifacts" / "mobile-failure.png"), full_page=True)
            finally:
                mobile.close()
        finally:
            browser.close()

    failed = [f"{suite}.{name}" for suite in ("desktop", "mobile") for name, passed in report[suite].items() if not passed]
    report["failed_checks"] = failed
    report["passed"] = not report["errors"] and not failed
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
