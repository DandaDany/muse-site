from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "multiday_locations.geojson"
FIXED_NOW_MS = 1786519200000
TAIPEI = {"lat": 25.0478, "lng": 121.5319}
TAIWAN = {"lat": 23.75, "lng": 121.0, "zoom": 8}


def install_fixture(page: Page, geo_mode: str) -> None:
    body = FIXTURE.read_text(encoding="utf-8")
    page.route(
        "**/data/locations.geojson",
        lambda route: route.fulfill(status=200, content_type="application/geo+json", body=body),
    )
    if geo_mode == "success":
        geo_body = f"""
          window.setTimeout(() => success({{
            coords: {{ latitude: {TAIPEI["lat"]}, longitude: {TAIPEI["lng"]}, accuracy: 20 }}
          }}), 0);
        """
    elif geo_mode == "outside":
        geo_body = """
          window.setTimeout(() => success({
            coords: { latitude: 35.6762, longitude: 139.6503, accuracy: 20 }
          }), 0);
        """
    elif geo_mode == "delayed":
        geo_body = f"""
          window.__geoRequested = true;
          window.__resolveStartupGeo = () => success({{
            coords: {{ latitude: {TAIPEI["lat"]}, longitude: {TAIPEI["lng"]}, accuracy: 20 }}
          }});
        """
    else:
        geo_body = """
          window.setTimeout(() => error({ code: 1, message: "Permission denied" }), 0);
        """

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
          Object.defineProperty(navigator, "geolocation", {{
            configurable: true,
            value: {{
              getCurrentPosition(success, error) {{
                {geo_body}
              }}
            }}
          }});
        }})()
        """,
    )


def open_page(context: BrowserContext, geo_mode: str) -> Page:
    page = context.new_page()
    install_fixture(page, geo_mode)
    page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
    page.locator("#summaryText").filter(has_text="更新於 8/12 07:05").wait_for()
    page.locator(".map-home-control").wait_for()
    return page


def viewport(page: Page) -> dict[str, float]:
    return page.evaluate(
        "() => { const c = map.getCenter(); return {lat: c.lat, lng: c.lng, zoom: map.getZoom()}; }"
    )


def near(actual: float, expected: float, tolerance: float = 0.03) -> bool:
    return abs(actual - expected) <= tolerance


def is_taiwan_overview(state: dict[str, float]) -> bool:
    return (
        near(state["lat"], TAIWAN["lat"], 0.08)
        and near(state["lng"], TAIWAN["lng"], 0.08)
        and state["zoom"] == TAIWAN["zoom"]
    )


def control_checks(page: Page) -> dict[str, bool]:
    home = page.locator(".map-home-control")
    zoom = page.locator(".leaflet-control-zoom")
    home_box = home.bounding_box()
    zoom_box = zoom.bounding_box()
    return {
        "home_exists_once": home.count() == 1,
        "home_directly_above_zoom": bool(
            home_box
            and zoom_box
            and home_box["y"] < zoom_box["y"]
            and abs(home_box["x"] - zoom_box["x"]) < 1
            and abs((home_box["y"] + home_box["height"]) - zoom_box["y"]) <= 2
        ),
        "legacy_home_removed": page.locator("#resetViewButton, #mHome").count() == 0,
    }


def run_desktop(browser: Browser, report: dict) -> None:
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, timezone_id="Asia/Taipei")
    page = open_page(context, "success")
    try:
        checks = report["desktop"]
        checks.update(control_checks(page))
        state = viewport(page)
        checks["startup_geolocation"] = (
            near(state["lat"], TAIPEI["lat"])
            and near(state["lng"], TAIPEI["lng"])
            and state["zoom"] == 10
        )
        checks["no_location_marker"] = (
            page.locator(".leaflet-marker-icon").count() == page.locator(".cinema-marker").count()
        )
        checks["selected_city_unchanged"] = page.evaluate("() => selectedCity === ''")

        page.locator(".leaflet-control-zoom-in").click()
        page.wait_for_timeout(350)
        zoomed_in = viewport(page)["zoom"]
        page.locator(".leaflet-control-zoom-out").click()
        page.wait_for_timeout(350)
        zoomed_out = viewport(page)["zoom"]
        checks["zoom_buttons_one_level"] = zoomed_in == 11 and zoomed_out == 10

        page.locator("#map").hover()
        page.mouse.wheel(0, -60)
        page.wait_for_timeout(450)
        wheel_zoom = viewport(page)["zoom"]
        checks["wheel_normal_scale"] = 11 <= wheel_zoom <= 12

        page.locator("#cityFilterList .filter-option").first.click()
        page.locator("#chainFilterList .filter-option").first.click()
        page.evaluate(
            """() => {
              mSearchInput.value = "威秀";
              mSearchInput.dispatchEvent(new Event("input", {bubbles: true}));
              setManualEarliest(1200);
            }"""
        )
        page.locator(".map-home-control-button").click()
        page.wait_for_timeout(500)
        home_state = viewport(page)
        checks["home_resets_view_and_filters"] = (
            is_taiwan_overview(home_state)
            and page.evaluate(
                "() => selectedCity === '' && selectedChain === '' && timeMode === 'auto' && timePeriod === 'all'"
            )
            and page.locator("#mSearchInput").input_value() == ""
            and page.locator(".leaflet-popup").count() == 0
        )
        page.screenshot(path=str(REPO / "artifacts" / "map-navigation-desktop.png"), full_page=True)
    finally:
        context.close()


def run_mobile(browser: Browser, report: dict) -> None:
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        timezone_id="Asia/Taipei",
        is_mobile=True,
        has_touch=True,
    )
    page = open_page(context, "success")
    try:
        checks = report["mobile"]
        checks.update(control_checks(page))
        state = viewport(page)
        checks["startup_geolocation"] = (
            near(state["lat"], TAIPEI["lat"])
            and near(state["lng"], TAIPEI["lng"])
            and state["zoom"] == 10
        )
        home_box = page.locator(".map-home-control").bounding_box()
        search_box = page.locator("#mSearch").bounding_box()
        checks["controls_clear_search"] = bool(
            home_box and search_box and home_box["y"] >= search_box["y"] + search_box["height"] + 6
        )
        checks["legacy_mobile_home_removed"] = page.locator("#mHome").count() == 0
        checks["pinch_zoom_enabled"] = page.evaluate("() => map.touchZoom.enabled()")

        session = context.new_cdp_session(page)
        before = viewport(page)["zoom"]
        session.send(
            "Input.dispatchTouchEvent",
            {
                "type": "touchStart",
                "touchPoints": [
                    {"x": 150, "y": 210, "radiusX": 2, "radiusY": 2},
                    {"x": 240, "y": 210, "radiusX": 2, "radiusY": 2},
                ],
            },
        )
        session.send(
            "Input.dispatchTouchEvent",
            {
                "type": "touchMove",
                "touchPoints": [
                    {"x": 115, "y": 210, "radiusX": 2, "radiusY": 2},
                    {"x": 275, "y": 210, "radiusX": 2, "radiusY": 2},
                ],
            },
        )
        session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        page.wait_for_timeout(550)
        after = viewport(page)["zoom"]
        checks["pinch_zoom_changes_view"] = before < after <= before + 3
        page.screenshot(path=str(REPO / "artifacts" / "map-navigation-mobile.png"), full_page=True)
    finally:
        context.close()


def run_fallbacks(browser: Browser, report: dict) -> None:
    for mode, key in (("denied", "permission_denied"), ("outside", "outside_taiwan")):
        context = browser.new_context(viewport={"width": 1200, "height": 900}, timezone_id="Asia/Taipei")
        page = open_page(context, mode)
        try:
            page.wait_for_timeout(250)
            report["geolocation"][key] = is_taiwan_overview(viewport(page))
        finally:
            context.close()


def run_delayed_interaction(browser: Browser, report: dict) -> None:
    context = browser.new_context(viewport={"width": 1200, "height": 900}, timezone_id="Asia/Taipei")
    page = open_page(context, "delayed")
    try:
        page.wait_for_function("() => window.__geoRequested === true")
        page.locator("#map").dispatch_event(
            "pointerdown", {"pointerType": "mouse", "button": 0, "clientX": 500, "clientY": 350}
        )
        before = viewport(page)
        page.evaluate("() => window.__resolveStartupGeo()")
        page.wait_for_timeout(300)
        after = viewport(page)
        report["geolocation"]["delayed_interaction_cancels"] = (
            near(before["lat"], after["lat"], 1e-7)
            and near(before["lng"], after["lng"], 1e-7)
            and before["zoom"] == after["zoom"]
            and is_taiwan_overview(after)
        )
    finally:
        context.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report", type=Path, default=REPO / "artifacts" / "map-navigation-report.json"
    )
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {"desktop": {}, "mobile": {}, "geolocation": {}, "errors": []}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for name, runner in (
                ("desktop", run_desktop),
                ("mobile", run_mobile),
                ("fallbacks", run_fallbacks),
                ("delayed", run_delayed_interaction),
            ):
                try:
                    runner(browser, report)
                except Exception:
                    report["errors"].append({"suite": name, "traceback": traceback.format_exc()})
        finally:
            browser.close()

    failed = [
        f"{suite}.{name}"
        for suite in ("desktop", "mobile", "geolocation")
        for name, passed in report[suite].items()
        if not passed
    ]
    report["failed_checks"] = failed
    report["passed"] = not report["errors"] and not failed
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
