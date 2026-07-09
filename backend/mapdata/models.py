"""
mapdata.models — 唯讀對映現有 SQLite 資料庫（data/movie_map.sqlite）的 8 張表。

重要設計決策：
1. 所有 model 皆為 unmanaged（Meta.managed = False）：
   資料表由既有的 sql/schema.sql 建立與維護，Django 絕不產生 migration、
   絕不修改現有 schema、不搬動資料庫。
2. 日期／時間類欄位（show_date、start_time、end_time、release_date、
   export_date、started_at、finished_at、fetched_at、created_at、updated_at 等）
   在 SQLite 中皆以 TEXT 儲存（格式不保證一致，例如 CURRENT_TIMESTAMP 的
   'YYYY-MM-DD HH:MM:SS' 或爬蟲寫入的自訂格式），因此一律用
   CharField(max_length=64, null=True, blank=True) 對映，
   避免 Django 的 DateField/DateTimeField 解析失敗而讓後台整頁炸掉。
3. 外鍵一律 on_delete=models.DO_NOTHING：
   FK 的級聯行為（CASCADE / SET NULL）由資料庫本身的 schema 管理，
   Django 端不重複實作，避免與 DB 行為衝突。
4. 布林旗標（active、all_locations_assumed_showing）在 SQLite 以 0/1 整數儲存，
   用 BooleanField 對映即可正確轉換。
"""

from django.db import models


class CinemaChain(models.Model):
    """影城連鎖品牌（cinema_chains）"""

    id = models.AutoField(primary_key=True)
    chain_name = models.CharField("連鎖名稱", max_length=255)
    official_url = models.CharField("官方網站", max_length=255, null=True, blank=True)
    crawl_url = models.CharField("爬蟲來源網址", max_length=255, null=True, blank=True)
    booking_url = models.CharField("訂票網址", max_length=255, null=True, blank=True)
    # 是否假設「全連鎖所有影城皆上映」（SQLite 以 0/1 儲存）
    all_locations_assumed_showing = models.BooleanField("預設全影城上映", default=True)
    notes = models.TextField("備註", null=True, blank=True)
    active = models.BooleanField("啟用", default=True)
    created_at = models.CharField("建立時間", max_length=64, null=True, blank=True)
    updated_at = models.CharField("更新時間", max_length=64, null=True, blank=True)

    class Meta:
        managed = False  # 資料表由既有 schema 管理，Django 不建立、不修改
        db_table = "cinema_chains"
        verbose_name = "影城連鎖"
        verbose_name_plural = "影城連鎖"

    def __str__(self):
        return self.chain_name


class CinemaLocation(models.Model):
    """影城據點（cinema_locations）"""

    id = models.AutoField(primary_key=True)
    chain = models.ForeignKey(
        CinemaChain,
        on_delete=models.DO_NOTHING,
        db_column="chain_id",
        related_name="locations",
        verbose_name="所屬連鎖",
    )
    location_name = models.CharField("據點名稱", max_length=255)
    display_name = models.CharField("顯示名稱", max_length=255, null=True, blank=True)
    address = models.TextField("地址", null=True, blank=True)
    city = models.CharField("縣市", max_length=255, null=True, blank=True)
    district = models.CharField("行政區", max_length=255, null=True, blank=True)
    latitude = models.FloatField("緯度", null=True, blank=True)
    longitude = models.FloatField("經度", null=True, blank=True)
    source_location_code = models.CharField("來源據點代碼", max_length=255, null=True, blank=True)
    location_url = models.CharField("據點網址", max_length=255, null=True, blank=True)
    source_url = models.CharField("來源網址", max_length=255, null=True, blank=True)
    notes = models.TextField("備註", null=True, blank=True)
    active = models.BooleanField("啟用", default=True)
    created_at = models.CharField("建立時間", max_length=64, null=True, blank=True)
    updated_at = models.CharField("更新時間", max_length=64, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "cinema_locations"
        verbose_name = "影城據點"
        verbose_name_plural = "影城據點"

    def __str__(self):
        return self.display_name or self.location_name


class Movie(models.Model):
    """電影（movies）"""

    id = models.AutoField(primary_key=True)
    title = models.CharField("片名", max_length=255)
    original_title = models.CharField("原文片名", max_length=255, null=True, blank=True)
    release_date = models.CharField("上映日期", max_length=64, null=True, blank=True)
    notes = models.TextField("備註", null=True, blank=True)
    active = models.BooleanField("啟用", default=True)
    created_at = models.CharField("建立時間", max_length=64, null=True, blank=True)
    updated_at = models.CharField("更新時間", max_length=64, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "movies"
        verbose_name = "電影"
        verbose_name_plural = "電影"

    def __str__(self):
        return self.title


class MovieTarget(models.Model):
    """電影追蹤目標（movie_targets）：某部電影在某連鎖／某據點的上映追蹤狀態"""

    id = models.AutoField(primary_key=True)
    movie = models.ForeignKey(
        Movie,
        on_delete=models.DO_NOTHING,
        db_column="movie_id",
        related_name="targets",
        verbose_name="電影",
    )
    chain = models.ForeignKey(
        CinemaChain,
        on_delete=models.DO_NOTHING,
        db_column="chain_id",
        related_name="movie_targets",
        verbose_name="影城連鎖",
    )
    location = models.ForeignKey(
        CinemaLocation,
        on_delete=models.DO_NOTHING,
        db_column="location_id",
        null=True,
        blank=True,
        related_name="movie_targets",
        verbose_name="影城據點",
    )
    # schema 有 CHECK 限制：'chain_all_locations' / 'single_location'
    target_scope = models.CharField("追蹤範圍", max_length=255)
    # schema 有 CHECK 限制：'assumed_showing' / 'confirmed_showing' / 'not_showing' / 'unknown'
    status = models.CharField("狀態", max_length=255)
    notes = models.TextField("備註", null=True, blank=True)
    created_at = models.CharField("建立時間", max_length=64, null=True, blank=True)
    updated_at = models.CharField("更新時間", max_length=64, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "movie_targets"
        verbose_name = "電影追蹤目標"
        verbose_name_plural = "電影追蹤目標"

    def __str__(self):
        return f"{self.movie} @ {self.location or self.chain}"


class Showtime(models.Model):
    """場次（showtimes）"""

    id = models.AutoField(primary_key=True)
    movie = models.ForeignKey(
        Movie,
        on_delete=models.DO_NOTHING,
        db_column="movie_id",
        related_name="showtimes",
        verbose_name="電影",
    )
    location = models.ForeignKey(
        CinemaLocation,
        on_delete=models.DO_NOTHING,
        db_column="location_id",
        related_name="showtimes",
        verbose_name="影城據點",
    )
    # CrawlRun 定義在本 model 之後，用字串參照解決前向參照
    crawl_run = models.ForeignKey(
        "CrawlRun",
        on_delete=models.DO_NOTHING,
        db_column="crawl_run_id",
        null=True,
        blank=True,
        related_name="showtimes",
        verbose_name="爬蟲批次",
    )
    show_date = models.CharField("放映日期", max_length=64, null=True, blank=True)
    start_time = models.CharField("開始時間", max_length=64, null=True, blank=True)
    end_time = models.CharField("結束時間", max_length=64, null=True, blank=True)
    auditorium = models.CharField("影廳", max_length=255, null=True, blank=True)
    format = models.CharField("放映格式", max_length=255, null=True, blank=True)
    language = models.CharField("語言", max_length=255, null=True, blank=True)
    subtitle = models.CharField("字幕", max_length=255, null=True, blank=True)
    booking_url = models.CharField("訂票網址", max_length=255, null=True, blank=True)
    source_url = models.CharField("來源網址", max_length=255, null=True, blank=True)
    raw_text = models.TextField("原始文字", null=True, blank=True)
    created_at = models.CharField("建立時間", max_length=64, null=True, blank=True)
    updated_at = models.CharField("更新時間", max_length=64, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "showtimes"
        verbose_name = "場次"
        verbose_name_plural = "場次"

    def __str__(self):
        return f"{self.movie} {self.show_date} {self.start_time} @ {self.location}"


class CrawlRun(models.Model):
    """爬蟲執行批次（crawl_runs）"""

    id = models.AutoField(primary_key=True)
    # schema 有 CHECK 限制：'locations' / 'showtimes' / 'kml_export' / 'other'
    run_type = models.CharField("批次類型", max_length=255)
    movie = models.ForeignKey(
        Movie,
        on_delete=models.DO_NOTHING,
        db_column="movie_id",
        null=True,
        blank=True,
        related_name="crawl_runs",
        verbose_name="電影",
    )
    source_name = models.CharField("來源名稱", max_length=255, null=True, blank=True)
    source_url = models.CharField("來源網址", max_length=255, null=True, blank=True)
    started_at = models.CharField("開始時間", max_length=64, null=True, blank=True)
    finished_at = models.CharField("結束時間", max_length=64, null=True, blank=True)
    # schema 有 CHECK 限制：'running' / 'success' / 'failed' / 'partial'
    status = models.CharField("狀態", max_length=255)
    rows_found = models.IntegerField("發現筆數", null=True, blank=True)
    rows_saved = models.IntegerField("儲存筆數", null=True, blank=True)
    error_message = models.TextField("錯誤訊息", null=True, blank=True)

    class Meta:
        managed = False
        db_table = "crawl_runs"
        verbose_name = "爬蟲批次"
        verbose_name_plural = "爬蟲批次"

    def __str__(self):
        return f"#{self.id} {self.run_type} ({self.status})"


class RawPage(models.Model):
    """原始網頁快照（raw_pages）"""

    id = models.AutoField(primary_key=True)
    crawl_run = models.ForeignKey(
        CrawlRun,
        on_delete=models.DO_NOTHING,
        db_column="crawl_run_id",
        null=True,
        blank=True,
        related_name="raw_pages",
        verbose_name="爬蟲批次",
    )
    source_url = models.CharField("來源網址", max_length=255)
    local_path = models.TextField("本機檔案路徑", null=True, blank=True)
    content_sha256 = models.TextField("內容 SHA-256", null=True, blank=True)
    http_status = models.IntegerField("HTTP 狀態碼", null=True, blank=True)
    fetched_at = models.CharField("抓取時間", max_length=64, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "raw_pages"
        verbose_name = "原始網頁"
        verbose_name_plural = "原始網頁"

    def __str__(self):
        return self.source_url


class KmlExport(models.Model):
    """KML 匯出紀錄（kml_exports）"""

    id = models.AutoField(primary_key=True)
    movie = models.ForeignKey(
        Movie,
        on_delete=models.DO_NOTHING,
        db_column="movie_id",
        null=True,
        blank=True,
        related_name="kml_exports",
        verbose_name="電影",
    )
    export_date = models.CharField("匯出日期", max_length=64, null=True, blank=True)
    file_path = models.CharField("檔案路徑", max_length=255)
    placemark_count = models.IntegerField("地標數量", null=True, blank=True)
    created_at = models.CharField("建立時間", max_length=64, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "kml_exports"
        verbose_name = "KML 匯出"
        verbose_name_plural = "KML 匯出"

    def __str__(self):
        return self.file_path
