# My Map 電影上映地圖

這個專案用來把「電影上映影城 + 場次」整理成 Google My Maps 可匯入的 KML。

## 專案決策紀錄

已確認採用的技術與重要實作決策記錄在：

```text
DECISIONS.md
```

包含 Leaflet、Playwright、GeoJSON、GitHub Pages、影城 logo marker 使用 `background-image` 等決策。後續修改架構或新增重要技術時，請同步更新該檔案。

## 目前資料庫設計

- `cinema_chains`：影城品牌與官方/場次來源連結。
- `cinema_locations`：影城據點、地址、經緯度，之後會變成地圖點。
- `movies`：目標電影。
- `movie_targets`：某部電影在哪些影城或據點上映。若先假設全據點上映，會使用 `chain_all_locations`。
- `showtimes`：每個據點的場次時間、格式、語言、訂票連結。
- `crawl_runs` / `raw_pages`：保留爬蟲執行紀錄，方便查錯。
- `kml_exports`：KML 匯出紀錄。

## 初始化資料庫

```powershell
python scripts/init_db.py
```

預設會建立：

```text
data/movie_map.sqlite
```

## 匯入影城清單

先編輯：

```text
data/input/cinema_sources.csv
```

最少只要填：

```csv
chain_name,official_url,all_locations_assumed_showing
威秀影城,https://www.vscinemas.com.tw/,1
```

然後執行：

```powershell
python scripts/import_cinema_sources.py
```

若是初始建檔、要用 CSV 直接覆蓋既有影城品牌與據點：

```powershell
python scripts/import_cinema_sources.py --replace
```

## 匯入威秀據點

威秀場次頁：

```text
https://www.vscinemas.com.tw/ShowTimes/
```

目前已先從頁面可見的下拉選單整理出威秀與 MUVIE 據點：

```powershell
python scripts/import_cinema_sources.py data/input/vieshow_locations.csv
```

或使用可視化瀏覽器直接抓下拉選單與影城代碼：

```powershell
python scripts/fetch_vieshow_locations.py
```

注意：`(GC)`、`(MUCROWN)` 目前保留成獨立來源據點，之後匯出 KML 時可再合併到同一實體影城點。

## 匯入手動補充 URL

你補上的特定據點入口會放在：

```text
data/input/manual_location_urls.csv
```

匯入：

```powershell
python scripts/import_cinema_sources.py data/input/manual_location_urls.csv
```

## 匯入秀泰據點

秀泰可由前端 bootstrap API 取得所有場館資料，包含 `cid`、地址與經緯度。預設會用執行當天產生場次入口 URL：

```powershell
python scripts/fetch_showtimes_locations.py
```

若要回補指定日期，可加 `--date YYYY-MM-DD`。

## 匯入國賓據點

國賓 TheaterList 可取得多數場館名稱、地址與 Showtime ID，Showtime 側欄可補完整場館清單。預設會用執行當天產生 Showtime URL：

```powershell
python scripts/fetch_ambassador_locations.py
```

若要回補指定日期，可加 `--date YYYY-MM-DD`。

## 匯入新光據點

新光 `films` 頁會在瀏覽器中呼叫 `GetAllForApp` API，可取得場館 ID、名稱、電話與經緯度：

```powershell
python scripts/fetch_skcinemas_locations.py
```

若要看可視化瀏覽器：

```powershell
python scripts/fetch_skcinemas_locations.py --headed
```

## 匯入 in89 據點

in89 首頁下拉選單可取得 TheaterId 與場館名稱：

```powershell
python scripts/fetch_in89_locations.py
```

目前 in89 地址尚未穩定出現在可直接解析的資料源，先保留城市與場館入口 URL。

## 匯入喜樂時代據點

喜樂時代票務首頁可取得各館 slug 入口：

```powershell
python scripts/fetch_centuryasia_locations.py
```

目前場次會落在各館的 `movie_timetable.aspx?ProgramID=...` 電影頁，之後做場次爬蟲時再深入解析。

## 匯入美麗新與小型/單店影城據點

美麗新可由 `Booking/Timetable` 頁面的 `CinemaList` 取得目前下拉選單據點；天台、威尼斯、百老匯、親親、王牌映画、環球中華、高雄環球、中影屏東、新月豪華、日新、金獅目前先以固定官方入口建立據點。預設日期型入口會使用執行當天：

```powershell
python scripts/fetch_misc_locations.py
```

若已先快取美麗新頁面 HTML，可離線解析：

```powershell
python scripts/fetch_misc_locations.py --miranew-html data/output/miranew_timetable.html
```

這支腳本目前會匯入：美麗新台茂、美麗新大直皇家、三重天台、桃園中壢威尼斯、公館百老匯、竹北百老匯、親親影城、王牌映画廣三 SOGO、斗六環球中華、高雄環球、中影屏東、宜蘭新月豪華、羅東日新本館、羅東日新統一廳、金門金獅。

## 查看資料庫筆數

```powershell
python scripts/inspect_db.py
```

## 匯出 KML

先匯出目前可定位的影城據點：

```powershell
python scripts/export_kml.py
```

指定日期：

```powershell
python scripts/export_kml.py --date YYYY-MM-DD
```

輸出位置預設在：

```text
data/output/kml/
```

目前 KML 每個點會包含：

- 地圖點名稱：品牌 + 影城據點。
- 地址：若有地址，會寫入 KML 的 `address`。
- 經緯度：若資料庫已有經緯度，會寫入 KML `Point`。
- 說明欄：品牌、影城名稱、地址、場次/影城入口、官方網站。
- ExtendedData：`location_id`、`chain_name`、`location_name`、`address`、`city`、`location_url`、`official_url`。

等場次爬蟲寫入 `showtimes` 後，可用電影名稱匯出當天場次 KML：

```powershell
python scripts/export_kml.py --movie-title "電影名稱"
```

場次 KML 會以「一個影城據點一個點」呈現，說明欄列出該影城當天所有場次時間。

## 抓取指定電影今日場次

目前可用總控腳本：

```powershell
python scripts/fetch_movie_showtimes.py "玩具總動員5" --date 2026-06-26
```

腳本會寫入 `movies`、`crawl_runs`、`showtimes`，並保留各來源原始回應到：

```text
data/output/showtimes/
```

目前第一版已接上：秀泰、國賓、美麗新、親親、王牌映画；百老匯、高雄環球、新月、日新 parser 已加入程式，待下次可連線時重跑追加。威秀 / MUVIE 與新光需再補專門場次 API。

更新本機地圖為指定電影場次：

```powershell
python scripts/export_geojson.py --movie-title "玩具總動員5" --date 2026-06-26
```

指定電影場次版 `web/data/locations.geojson` 只會包含有場次的影城點，並在每個點的 `showtimes` 欄位列出時間、格式、語言與影廳。

## 本機網頁地圖

先輸出前端用 GeoJSON：

```powershell
python scripts/export_geojson.py
```

啟動本機地圖：

```powershell
cd web
python -m http.server 8765 --bind 127.0.0.1
```

瀏覽：

```text
http://127.0.0.1:8765/
```

目前網頁地圖會載入 84 個影城據點，提供搜尋、品牌篩選、縣市篩選，地圖初始視角以台灣為中心，拖曳範圍限制在台灣與離島附近。品牌篩選依據點數由大到小排序，縣市篩選依台北起逆時針繞台排序，兩個篩選清單一次顯示約 5 筆，其餘可捲動。

## 補齊經緯度

若新增影城據點後缺經緯度，可執行：

```powershell
python scripts/geocode_locations.py
```

這支腳本會先套用已知地址覆寫表，再使用 ArcGIS / Nominatim 地理編碼補 `latitude`、`longitude`。查詢紀錄會輸出到：

```text
data/output/geocode_results_YYYY-MM-DD.csv
```

若只想測試、不寫回資料庫：

```powershell
python scripts/geocode_locations.py --dry-run --limit 5
```

## 下一步

等你提供正式的影城名稱與影城連結後，下一步會做：

1. 匯入影城品牌清單。
2. 爬每個影城的所有據點。
3. 補上地址與經緯度。
4. 建立指定電影的 `movie_targets`，先標記為「全部據點假設上映」。
5. 接場次爬蟲，寫入 `showtimes`。
6. 匯出 KML 給 Google My Maps。

## 2026-06-26 場次來源狀態

`scripts/fetch_movie_showtimes.py` 目前主流程已接入 19 個影城系統：

- 威秀影城 / VIESHOW + MUVIE CINEMAS
- 秀泰影城
- 國賓影城
- 新光影城
- in89 豪華影城
- 喜樂時代影城
- 美麗新影城
- 天台影城
- 威尼斯影城
- 百老匯影城
- 親親影城 / 親親戲院
- 王牌映画影城
- 環球中華影城
- 高雄環球影城
- 中影屏東影城
- 新月豪華影城
- 日新戲院 / 宜蘭電影資訊網
- 金獅影城

新光影城會先用 Playwright 擷取官方 API 所需的短效 headers，再呼叫 `GetSessionByCinemasIDForApp`。in89 會從各據點頁面的 `theater_api` 取得分館 API，再呼叫 `getStagesByDate`。威秀/MUVIE、喜樂時代、天台、威尼斯、環球中華、中影屏東已接入 parser，但仍需要實際網路環境驗證場次數量。
