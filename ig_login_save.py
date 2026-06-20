"""
登入 Instagram 並將 session 狀態儲存到 ig_state.json。
需先在 .env 設定 IG_USERNAME 與 IG_PASSWORD。
"""

import os
import re
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")
STATE_FILE = "ig_state.json"

COOKIE_SELECTORS = [
    "button:has-text('Allow all cookies')",
    "button:has-text('Only allow essential cookies')",
    "button:has-text('允許所有 Cookie')",
    "button:has-text('只允許必要 Cookie')",
    "button:has-text('接受所有')",
]


def click_if_exists(page, selector, timeout=3000):
    try:
        page.locator(selector).click(timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        return False


def main():
    if not IG_USERNAME or not IG_PASSWORD:
        raise ValueError("請先在 .env 裡設定 IG_USERNAME 和 IG_PASSWORD")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="zh-TW",
            timezone_id="Asia/Taipei",
        )
        page = context.new_page()

        page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        for selector in COOKIE_SELECTORS:
            if click_if_exists(page, selector, timeout=1500):
                print(f"已按下 Cookie 按鈕：{selector}")
                break

        page.locator("input[name='username']").fill(IG_USERNAME)
        page.locator("input[name='password']").fill(IG_PASSWORD)
        page.locator("button[type='submit']").click()

        print("如果 IG 要求驗證碼、2FA、信任此裝置，請在瀏覽器手動完成。")
        print("完成後程式會自動儲存登入狀態。")

        try:
            page.wait_for_url(
                re.compile(
                    r"https://www\.instagram\.com/($|accounts/onetap/|challenge/|accounts/login/two_factor)"
                ),
                timeout=60000,
            )
        except PlaywrightTimeoutError:
            pass

        page.wait_for_timeout(10000)

        if "instagram.com" in page.url and "/accounts/login" not in page.url:
            print("目前網址：", page.url)
        else:
            print("目前網址：", page.url)
            input("如果還沒登入完成，請手動完成後按 Enter 繼續：")

        context.storage_state(path=STATE_FILE)
        print(f"已儲存登入狀態到：{STATE_FILE}")

        browser.close()


if __name__ == "__main__":
    main()
