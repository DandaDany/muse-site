"""
使用已儲存的 ig_state.json session 開啟 Instagram，免重新登入。
需先執行 ig_login_save.py 產生 ig_state.json。
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_FILE = "ig_state.json"


def main():
    if not Path(STATE_FILE).exists():
        raise FileNotFoundError(
            f"找不到 {STATE_FILE}，請先執行 ig_login_save.py 儲存登入狀態"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(
            storage_state=STATE_FILE,
            viewport={"width": 1280, "height": 900},
            locale="zh-TW",
            timezone_id="Asia/Taipei",
        )
        page = context.new_page()

        page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        print("目前頁面標題：", page.title())
        print("目前網址：", page.url)

        if "accounts/login" in page.url:
            print("警告：Session 已失效，請重新執行 ig_login_save.py")
            browser.close()
            return

        input("按 Enter 關閉瀏覽器：")
        browser.close()


if __name__ == "__main__":
    main()
