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
        initial_marker_count = page.locator(".cinema-marker").count()

        page.locator(".basemap-option").last.click()
        page.wait_for_timeout(3_000)
        page.locator("#searchInput").fill("台")
        page.wait_for_selector(".suggestion-row", timeout=10_000)
        search_suggestion_count = page.locator(".suggestion-row").count()
        page.locator(".suggestion-row").first.click()
        page.wait_for_selector(".leaflet-popup", timeout=10_000)
        popup_after_search = page.locator(".leaflet-popup").count()
        page.keyboard.press("Escape")
        page.locator(".cinema-marker").first.click()
        page.wait_for_selector(".leaflet-popup", timeout=10_000)
        popup_after_marker = page.locator(".leaflet-popup").count()
        page.screenshot(path=str(SCREENSHOT), full_page=True)

        result = {
            "initialMarkers": initial_marker_count,
            "filteredMarkers": page.locator(".cinema-marker").count(),
            "searchSuggestions": search_suggestion_count,
            "popupAfterSearch": popup_after_search,
            "popupAfterMarker": popup_after_marker,
            "basemaps": page.locator(".basemap-option").count(),
            "selectedBasemap": page.locator(".basemap-option.is-selected span").inner_text(),
            "zoom": page.evaluate(
                "() => ({"
                "zoomDelta: map.options.zoomDelta,"
                "zoomSnap: map.options.zoomSnap,"
                "scrollWheelZoom: map.options.scrollWheelZoom,"
                "wheelDebounceTime: map.options.wheelDebounceTime,"
                "wheelPxPerZoomLevel: map.options.wheelPxPerZoomLevel,"
                "zoomAnimation: map.options.zoomAnimation,"
                "fadeAnimation: map.options.fadeAnimation,"
                "markerZoomAnimation: map.options.markerZoomAnimation"
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
