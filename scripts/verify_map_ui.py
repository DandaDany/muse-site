from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = "http://127.0.0.1:8765/"
SCREENSHOT = Path("data/output/map_screenshot_2026-06-26_basemap_options.png")


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
        errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

        page.goto(URL, wait_until="networkidle", timeout=45_000)
        page.wait_for_selector(".cinema-marker", timeout=20_000)
        page.wait_for_selector(".basemap-option", timeout=10_000)

        page.locator(".basemap-option").last.click()
        page.wait_for_timeout(3_000)
        page.screenshot(path=str(SCREENSHOT), full_page=True)

        result = {
            "markers": page.locator(".cinema-marker").count(),
            "rows": page.locator(".location-row").count(),
            "basemaps": page.locator(".basemap-option").count(),
            "selectedBasemap": page.locator(".basemap-option.is-selected span").inner_text(),
            "zoom": page.evaluate(
                "() => ({"
                "zoomDelta: map.options.zoomDelta,"
                "zoomSnap: map.options.zoomSnap,"
                "scrollWheelZoom: map.options.scrollWheelZoom"
                "})"
            ),
            "wheelConstants": page.evaluate(
                "() => ({"
                "buttonStep: ZOOM_BUTTON_STEP,"
                "snapStep: ZOOM_SNAP_STEP,"
                "wheelSensitivity: WHEEL_ZOOM_SENSITIVITY,"
                "wheelEase: WHEEL_ZOOM_EASE,"
                "stopThreshold: WHEEL_ZOOM_STOP_THRESHOLD,"
                "resetMs: WHEEL_TARGET_RESET_MS"
                "})"
            ),
            "tiles": page.evaluate(
                "() => Array.from(document.querySelectorAll('img.leaflet-tile')).map((img) => ({"
                "src: img.src,"
                "loaded: img.complete && img.naturalWidth > 0,"
                "naturalWidth: img.naturalWidth,"
                "naturalHeight: img.naturalHeight,"
                "visibility: getComputedStyle(img).visibility,"
                "opacity: getComputedStyle(img).opacity"
                "}))"
            ),
            "errors": errors,
            "screenshot": str(SCREENSHOT),
        }
        browser.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
