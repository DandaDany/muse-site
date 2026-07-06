-- 手動地點覆寫：新光影城 5 據點的地址與精準經緯度
--
-- 背景：skcinemas API 未提供地址，且台北天母的經緯度有誤（落在山區）。
-- 這份 SQL 以使用者提供的正確資料覆寫 cinema_locations。
--
-- 用法（在專案根目錄，資料抓取／匯出「之前」執行，或每次 fetch 後補跑一次）：
--   sqlite3 data/movie_map.sqlite < sql/manual_location_overrides.sql
--
-- 之後再跑 scripts/export_geojson.py（或 更新地圖.bat）即可讓地圖同步。

UPDATE cinema_locations
SET address = '台北市萬華區西寧南路36號4-5樓（獅子林大樓）', latitude = 25.045591, longitude = 121.506640
WHERE location_name = '新光影城台北獅子林';

UPDATE cinema_locations
SET address = '台北市士林區忠誠路二段202號4樓（新光三越台北天母店B棟）', latitude = 25.118000, longitude = 121.534200
WHERE location_name = '新光影城台北天母';

UPDATE cinema_locations
SET address = '桃園市中壢區春德路107號3-5樓（置地廣場·桃園）', latitude = 25.017327, longitude = 121.213758
WHERE location_name = '新光影城桃園青埔';

UPDATE cinema_locations
SET address = '台中市西屯區臺灣大道三段301號14樓（新光三越台中中港店）', latitude = 24.165260, longitude = 120.643710
WHERE location_name = '新光影城台中中港';

UPDATE cinema_locations
SET address = '台南市中西區西門路一段658號9樓（新光三越台南新天地）', latitude = 22.986882, longitude = 120.197693
WHERE location_name = '新光影城台南西門';
