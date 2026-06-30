from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from init_db import DEFAULT_DB_PATH


PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_DIR / "data" / "output" / "debug_vieshow"
VIESHOW_URL = "https://www.vscinemas.com.tw/ShowTimes/"

MOVIE_ALIASES = [
    "玩具總動員5",
    "玩具總動員５",
    "玩具總動員 5",
    "Toy Story 5",
]


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    table = str.maketrans("０１２３４５６７８９", "0123456789")
    value = value.translate(table).lower()
    return re.sub(r"[\s　:：,，.。()（）\[\]【】\-–—_．・‧|｜]+", "", value)


def movie_matches(text: str) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(alias) in normalized for alias in MOVIE_ALIASES)


def get_vieshow_locations(db_path: Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                cl.id,
                cc.chain_name,
                cl.location_name,
                cl.source_location_code,
                cl.location_url
            FROM cinema_locations cl
            JOIN cinema_chains cc ON cc.id = cl.chain_id
            WHERE cc.chain_name IN ('威秀影城 / VIESHOW', 'MUVIE CINEMAS')
              AND cl.active = 1
              AND cl.source_location_code IS NOT NULL
            ORDER BY cc.chain_name, cl.location_name
            """
        ).fetchall()

    return rows


def inspect_selects(page) -> None:
    select_count = page.locator("select").count()
    print(f"\n[PAGE] select count = {select_count}")

    for i in range(select_count):
        try:
            info = page.locator("select").nth(i).evaluate(
                """
                select => ({
                    id: select.id || "",
                    name: select.getAttribute("name") || "",
                    className: select.className || "",
                    visible: !!(select.offsetWidth || select.offsetHeight || select.getClientRects().length),
                    optionCount: select.options.length,
                    options: Array.from(select.options).slice(0, 12).map(o => ({
                        value: (o.value || "").trim(),
                        text: (o.textContent || "").trim()
                    }))
                })
                """
            )

            print(
                f"\n[SELECT {i}] "
                f"id={info['id']} "
                f"name={info['name']} "
                f"class={info['className']} "
                f"visible={info['visible']} "
                f"optionCount={info['optionCount']}"
            )

            for opt in info["options"]:
                print(f"  - value={opt['value']} text={opt['text']}")

        except Exception as exc:
            print(f"[SELECT {i}] inspect failed: {exc}")


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
            print(f"[SELECT DEBUG] normal select failed selector={selector} code={code} error={exc}")

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

def analyze_html(html_text: str) -> dict[str, object]:
    soup = BeautifulSoup(html_text, "html.parser")
    page_text = soup.get_text("\n", strip=True)

    has_access_denied = "Access Denied" in html_text
    has_movie_by_html = any(alias in html_text for alias in MOVIE_ALIASES)
    has_movie_by_text = movie_matches(page_text)
    time_count = len(re.findall(r"\b\d{1,2}:\d{2}\b", page_text))

    matched_lines = []
    for line in page_text.splitlines():
        line = line.strip()
        if not line:
            continue

        if movie_matches(line) or re.search(r"\b\d{1,2}:\d{2}\b", line):
            matched_lines.append(line)

        if len(matched_lines) >= 40:
            break

    return {
        "has_access_denied": has_access_denied,
        "has_movie_by_html": has_movie_by_html,
        "has_movie_by_text": has_movie_by_text,
        "time_count": time_count,
        "matched_lines": matched_lines,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = get_vieshow_locations()
    print(f"[DB] VIESHOW/MUVIE locations = {len(rows)}")

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

        html = page.content()
        print("[PAGE] title =", page.title())
        print("[PAGE] access denied =", "Access Denied" in html)

        inspect_selects(page)

        summary = []

        for row in rows:
            location_id = int(row["id"])
            chain_name = row["chain_name"]
            location_name = row["location_name"]
            code = str(row["source_location_code"])

            print("\n" + "=" * 80)
            print(f"[TRY] id={location_id} chain={chain_name} code={code} location={location_name}")

            ok, message = select_vieshow_location(page, code)
            print(f"[SELECT] ok={ok} message={message}")

            html_text = page.content()

            safe_name = re.sub(
                r"[^\w.-]+",
                "_",
                f"{code}_{location_name}",
                flags=re.UNICODE,
            ).strip("_")

            output_path = OUTPUT_DIR / f"{safe_name}.html"
            output_path.write_text(html_text, encoding="utf-8")

            result = analyze_html(html_text)

            print(f"[RESULT] access_denied={result['has_access_denied']}")
            print(f"[RESULT] has_movie_by_html={result['has_movie_by_html']}")
            print(f"[RESULT] has_movie_by_text={result['has_movie_by_text']}")
            print(f"[RESULT] time_count={result['time_count']}")
            print(f"[SAVED] {output_path}")

            print("[MATCHED LINES PREVIEW]")
            for line in result["matched_lines"]:
                print("  " + line)

            summary.append(
                {
                    "id": location_id,
                    "chain": chain_name,
                    "code": code,
                    "location": location_name,
                    "select_ok": ok,
                    "select_message": message,
                    "access_denied": result["has_access_denied"],
                    "has_movie": result["has_movie_by_text"],
                    "time_count": result["time_count"],
                    "html": str(output_path),
                }
            )

        print("\n" + "#" * 80)
        print("[SUMMARY]")

        for item in summary:
            print(
                f"{item['code']} | {item['location']} | "
                f"select_ok={item['select_ok']} | "
                f"movie={item['has_movie']} | "
                f"time_count={item['time_count']} | "
                f"{item['select_message']}"
            )

        summary_path = OUTPUT_DIR / "summary.txt"

        with summary_path.open("w", encoding="utf-8") as f:
            for item in summary:
                f.write(
                    f"{item['code']}\t"
                    f"{item['chain']}\t"
                    f"{item['location']}\t"
                    f"select_ok={item['select_ok']}\t"
                    f"movie={item['has_movie']}\t"
                    f"time_count={item['time_count']}\t"
                    f"{item['select_message']}\t"
                    f"{item['html']}\n"
                )

        print(f"\n[SUMMARY SAVED] {summary_path}")

        input("\n檢查完後按 Enter 關閉瀏覽器...")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()