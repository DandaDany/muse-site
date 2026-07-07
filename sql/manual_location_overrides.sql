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

-- 秀泰影城 14 據點的精準經緯度覆寫
--
-- 背景：秀泰多數據點原本的經緯度是匯入時的估算/湊整值，部分嚴重偏移
-- （例：土城落到關西山區、麗寶偏移約 11km、台南仁德與北港為湊整值）。
-- 這份覆寫以使用者提供並經行政區健全性檢查的座標修正。
-- 台中站前秀泰維持原值（已與維基百科標註一致），故不列入。
UPDATE cinema_locations SET latitude = 25.0441, longitude = 121.5606 WHERE location_name = '大巨蛋秀泰影城';
UPDATE cinema_locations SET latitude = 25.0536, longitude = 121.5262 WHERE location_name = '台北欣欣秀泰影城';
UPDATE cinema_locations SET latitude = 24.9839, longitude = 121.4447 WHERE location_name = '土城秀泰影城';
UPDATE cinema_locations SET latitude = 24.9930, longitude = 121.4277 WHERE location_name = '樹林秀泰影城';
UPDATE cinema_locations SET latitude = 24.1291, longitude = 120.6472 WHERE location_name = '台中文心秀泰影城';
UPDATE cinema_locations SET latitude = 24.3292, longitude = 120.6974 WHERE location_name = '台中麗寶秀泰影城';
UPDATE cinema_locations SET latitude = 23.4854, longitude = 120.4497 WHERE location_name = '嘉義秀泰影城';
UPDATE cinema_locations SET latitude = 25.1301, longitude = 121.7441 WHERE location_name = '基隆秀泰影城';
UPDATE cinema_locations SET latitude = 23.991195309806955, longitude = 121.6053562819217 WHERE location_name = '花蓮秀泰影城';
UPDATE cinema_locations SET latitude = 22.75231192297646, longitude = 121.1481239800308 WHERE location_name = '台東秀泰影城';
UPDATE cinema_locations SET latitude = 23.5756, longitude = 120.3015 WHERE location_name = '北港秀泰影城';
UPDATE cinema_locations SET latitude = 22.9576, longitude = 120.2291 WHERE location_name = '台南仁德秀泰影城';
UPDATE cinema_locations SET latitude = 22.7932, longitude = 120.3023 WHERE location_name = '高雄岡山秀泰影城';
UPDATE cinema_locations SET latitude = 22.5951, longitude = 120.3068 WHERE location_name = '高雄夢時代秀泰影城';
