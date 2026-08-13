from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "popup_regression_locations.geojson"
FIXED_NOW_MS = 1786519200000
HALAR_URL = "https://halarcity.com.tw/Browsing/Cinemas/Details/0000000001"


def install_fixture(page: Page) -> None:
    body = FIXTURE.read_text(encoding="utf-8")
    page.route("**/data/locations.geojson", lambda route: route.fulfill(
        status=200, content_type="application/geo+json", body=body
    ))
    page.add_init_script(f"""
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
    """)


def assert_chips(page: Page) -> None:
    assert page.locator("#dateChips .date-chip").all_text_contents() == ["今天 8/12", "明天 8/13"]


def open_marker(page: Page, prefix: str) -> None:
    page.locator(f".cinema-marker[aria-label^='{prefix}']").dispatch_event("click")


def assert_ambassador_popup(page: Page, expected_date: str) -> None:
    container = page.locator(".leaflet-popup") if page.viewport_size["width"] > 390 else page.locator("#mSheetBody")
    container.wait_for()
    assert container.locator(".pst-date").inner_text() == expected_date
    text = container.inner_text()
    assert "日語" in text
    assert "國語" in text
    assert "今天 8/12 2026/08/12" not in text
    assert "明天 8/13 2026/08/13" not in text


def run(page: Page, mobile: bool, report: dict) -> None:
    page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
    assert_chips(page)
    open_marker(page, "國賓影城")
    assert_ambassador_popup(page, "2026/08/12")

    page.locator("#dateChips button[data-date='2026-08-13']").dispatch_event("click")
    page.wait_for_timeout(400)
    assert_chips(page)
    assert_ambassador_popup(page, "2026/08/13")
    page.screenshot(
        path=str(REPO / "artifacts" / ("mobile-popup.png" if mobile else "desktop-popup.png")),
        full_page=True,
    )

    page.locator("#dateChips button[data-date='2026-08-12']").dispatch_event("click")
    page.wait_for_timeout(400)
    open_marker(page, "哈拉影城")
    container = page.locator("#mSheetBody") if mobile else page.locator(".leaflet-popup")
    link = container.get_by_role("link", name="場次入口")
    assert link.get_attribute("href") == HALAR_URL
    assert container.locator(".pst-date").inner_text() == "2026/08/12"
    report["mobile" if mobile else "desktop"] = {
        "popup_today": "2026/08/12",
        "popup_future": "2026/08/13",
        "date_chips": ["今天 8/12", "明天 8/13"],
        "ambassador_languages": ["日語", "國語"],
        "halar_href": link.get_attribute("href"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=REPO / "artifacts" / "targeted-browser-report.json")
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {"errors": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for mobile, viewport in ((False, {"width": 1440, "height": 1000}), (True, {"width": 390, "height": 844})):
                context = browser.new_context(
                    viewport=viewport, timezone_id="Asia/Taipei",
                    is_mobile=mobile, has_touch=mobile,
                )
                page = context.new_page()
                install_fixture(page)
                try:
                    run(page, mobile, report)
                except Exception:
                    report["errors"].append({
                        "suite": "mobile" if mobile else "desktop",
                        "traceback": traceback.format_exc(),
                    })
                    page.screenshot(
                        path=str(REPO / "artifacts" / ("mobile-popup-failure.png" if mobile else "desktop-popup-failure.png")),
                        full_page=True,
                    )
                finally:
                    context.close()
        finally:
            browser.close()
    report["passed"] = not report["errors"]
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
