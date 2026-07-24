"""把一組地址批次地理編碼成經緯度（重用 geocode_locations 的 ArcGIS/Nominatim 邏輯）。

用途：需要為新影城據點取得座標，但本機/沙箱無法連外地理編碼服務時，在
GitHub Actions（有開放網路）跑一次即可。輸出 CSV 方便貼回 data/input 的據點 CSV。

用法：
    python scripts/geocode_addresses.py "台北市萬華區峨眉街52號" "新北市永和區中山路一段238號"
    # 或每行一個地址從 stdin 讀：
    printf '%s\\n' "地址A" "地址B" | python scripts/geocode_addresses.py -
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geocode_locations import fetch_geocode  # noqa: E402


def main() -> None:
    args = sys.argv[1:]
    if args == ["-"] or not args:
        addresses = [line.strip() for line in sys.stdin if line.strip()]
    else:
        addresses = [a.strip() for a in args if a.strip()]

    print("[GEOCODE] address,latitude,longitude,provider,score,match")
    for address in addresses:
        try:
            result = fetch_geocode(address)
        except Exception as exc:  # noqa: BLE001 - 診斷用，逐筆回報錯誤即可
            print(f"[GEOCODE] {address},,,ERROR,,{type(exc).__name__}: {exc}")
            continue
        if not result:
            print(f"[GEOCODE] {address},,,NO_MATCH,,")
            continue
        print(
            f"[GEOCODE] {address},{result.get('latitude')},{result.get('longitude')},"
            f"{result.get('provider')},{result.get('score')},{result.get('display_name')}"
        )
        time.sleep(1)  # 對 Nominatim 友善的節流


if __name__ == "__main__":
    main()
