# P0-A 多日場次來源研究（2026-08-12）

## 判讀方式

- 先以雲端 Chrome 實際開啟每一個官方場次入口，查看／操作可見日期控制。
- 再以現有 crawler 的官方 HTML、JSON/API 與程式碼交叉核對資料取得方式及日期隔離能力。
- `+N` 代表以 2026-08-12 為第 0 天，最遠可見到 N 天後。
- P0 日期列只服務「連續一般上映時刻窗口」。零散遠期特殊預售不納入日期 chips，也不擴張一般週表 horizon。
- 「無法確認」不是「不支援」：代表當次被 502、Cloudflare、Queue-it、連線逾時或瀏覽器 URL policy 阻擋。

## 來源矩陣

| 來源 | 2026-08-12 實際可見最遠日 | 可切日期 | 資料型態 | 修改前 crawler 日期能力 | P0-A 處理 |
|---|---:|---|---|---|---|
| 威秀／MUVIE | 8/20（+8；官網說明週五至下週四） | 是 | Playwright + JS state | 接受日期，但每次重開瀏覽器 | 同次執行快取各館 HTML，再依日期切分 |
| 秀泰 | 8/22（+10） | 是 | JSON bootstrap API | 已依 `listedAt` 過濾 | 多日共用 API response cache |
| 國賓 | 8/20（+8） | 是 | URL `DT=YYYY/MM/DD` + HTML | 已支援 | 逐日 URL，保留原名稱／場次結構 |
| 新光 | 官網 502；無法以瀏覽器確認 | 是（API 有 BusinessDate/ShowDate） | 動態 API + 短效 headers | 已依日期過濾，但每次重取 headers | 未驗到 horizon，P0 只抓今天；adapter 已可共用 headers |
| in89 | 一般週表至 8/16；API另有 8/22、8/29、9/13 預售 | 是 | JSON API | 已依 date key 過濾 | 多日共用 API response；P0 保留一般週表 +4，零散特殊預售明確排除於日期列 |
| 喜樂時代 | 無法在入口頁直接確認 | 是 | Playwright；新版/舊版 JS active date | parser 會驗 active date，但不會切換 | 新增日期控制 adapter；未驗到 horizon，P0 只抓今天 |
| 美麗新 | 選館後才顯示；入口未顯示最遠日 | 是 | HTML 內嵌 JSON | 已依 `ShowDateISO` 過濾 | 未驗到 horizon，P0 只抓今天 |
| 天台 | 8/16（+4） | 不需切換 | 同一 HTML 直接列多日 | 文字日期鄰近過濾 | 多日共用 HTML cache |
| 哈拉 | Browser URL policy 阻擋；無法確認 | 是 | 同一 HTML 多日區塊 | 已依區塊日期過濾 | 未驗到 horizon，P0 只抓今天 |
| 美麗華 | 8/18（+6） | 同頁日期區塊 | HTML | 已依月／日 class 過濾 | 多日共用 HTML cache |
| 南台 | 官網 502；無法確認 | 是 | HTML option → `?day=` | 已由 option 找日期索引 | 未驗到 horizon，P0 只抓今天 |
| 樂聲 | 8/13（+1） | 同頁日期區塊 | HTML | 已依月／日過濾 | 多日共用 HTML cache |
| 台鋁 | 8/16（+4） | 同頁日期區塊 | HTML | 已依日期節點過濾 | 多日共用 HTML cache |
| 鴻金寶麻吉 | 8/13（+1） | 是 | TIXI HTML／JS state | 已由訂票 onclick 完整日期過濾 | 多日共用 HTML cache |
| 光點華山 | 連線逾時；無法確認 | 是 | TIXI HTML／JS state | 已由 onclick 日期過濾 | 未驗到 horizon，P0 只抓今天 |
| 微風 | 8/20（+8） | 是 | TIXI HTML select／POST | 已由 onclick 日期過濾 | 多日共用 HTML cache |
| 總督 | 8/20（+8） | 是 | TIXI HTML select／POST | 已由 onclick 日期過濾 | 多日共用 HTML cache |
| 誠品 | Cloudflare blocked；無法確認 | 同頁多日 | HTML | 已依日期 heading 過濾 | 未驗到 horizon，P0 只抓今天 |
| 南投 | 8/13（+1） | 是 | GET `search_date` | 已支援 | 逐日 URL |
| 埔里山明 | 需先選電影；入口未直接顯示日期 | 是 | HTML／電影 AJAX 區塊 | 已由日期範圍判斷 | 未驗到 horizon，P0 只抓今天 |
| 清水時代 | 官網 502；無法確認 | 同頁週表 | HTML | 已用日期範圍解析 | 未驗到 horizon，P0 只抓今天 |
| 威尼斯 | Cloudflare human verification | 是 | Playwright HTML | 已使用日期鄰近過濾 | 未驗到 horizon，P0 只抓今天 |
| 親親 | 8/13（+1） | 是 | 同一 HTML tabs | 已依日期 tab id 過濾 | 多日共用 HTML cache |
| 王牌映画 | 官網 502；無法確認 | 是 | 官方 HTML；@movies 日期 URL fallback | 官方只可靠抓 active date | P0 保守維持今天；列為未支援多日來源 |
| 環球中華 | 8/14（+2） | 是 | ASP.NET select/postback | 修改前只 GET selector，拿不到場次 | 新增 Playwright select/postback adapter |
| 百老匯 | 官網連線逾時；API可用 | 是 | JSON API | 已依 `showdate` 過濾 | 未驗到 horizon，P0 只抓今天 |
| 高雄環球 | Cloudflare human verification | 同頁多日 | HTML | 已依完整日期區塊過濾 | 未驗到 horizon，P0 只抓今天；主日期保留 unavailable 提示 |
| 中影屏東 | 連線逾時；無法確認 | 是 | URL `?date=`；@movies fallback | 已支援日期 | 未驗到 horizon，P0 只抓今天 |
| 新月豪華 | 8/16（+4） | 不需切換 | 同一 HTML 直接列多日 | **修改前把所有日期誤貼成請求日** | 以 `SHOW_DATELabel` 限定日期容器；新增回歸測試 |
| 日新／宜蘭電影資訊網 | 連線逾時；無法確認 | 同頁多日 | HTML | 已依月／日列過濾 | 未驗到 horizon，P0 只抓今天 |
| 金獅 | Cloudflare human verification | 同頁多日 | HTML | 已依完整日期行過濾 | 未驗到 horizon，P0 只抓今天 |

## 電影名稱與場次結構

- 同一來源跨日期通常沿用相同中文／英文片名與相同 session schema。
- 真正的差異在日期容器：URL parameter、API date key、HTML date block、active JS state、ASP.NET postback 五種不能混用。
- 新月豪華已證明「同一 HTML 多日」若只把請求日寫進 record，會產生跨日污染；P0-A 因此以 source date 作為必須驗證的資料邊界。
- 特殊預售可能產生不連續日期，但不屬於 P0 日期列產品範圍；未來若要支援，應另行設計「預售場次」，不得混入一般日期列。

## P0 抓取上限與後續風險

`scripts/showtime_availability.py` 記錄本輪觀察到的一般週表上限，作為網路請求 ceiling；它不決定 UI 天數。UI 只讀匯出後真正存在的日期。

in89 已看到 9 月特殊預售日期，但這不是 P0 漏抓：P0 的產品範圍刻意只涵蓋連續一般週表。若未來要支援預售，應建立獨立的「預售場次」資訊與互動，不把零散遠期日期混入本日期列。
