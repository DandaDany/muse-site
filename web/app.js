const TAIWAN_CENTER = [23.75, 121.0];
const TAIWAN_BOUNDS = L.latLngBounds([21.5, 117.7], [26.6, 123.2]);
// 手機底部有 40% 篩選底盤遮住地圖，南端（與北端）多留白，
// 才能把南部影城捲到底盤上方看見；桌機維持原本較緊的範圍。
const TAIWAN_BOUNDS_MOBILE = L.latLngBounds([20.0, 117.7], [26.9, 123.2]);

function activeMaxBounds() {
  return window.matchMedia("(max-width: 760px)").matches ? TAIWAN_BOUNDS_MOBILE : TAIWAN_BOUNDS;
}
const DATA_URL = "data/locations.geojson";
const LOGO_URL = "data/chain_logos.json";
const ZOOM_BUTTON_STEP = 0.5;
const ZOOM_SNAP_STEP = 0.25;
const MIN_MARKER_SIZE = 24;
const MAX_MARKER_SIZE = 48;
const CITY_ORDER = [
  "臺北市",
  "新北市",
  "桃園市",
  "新竹市",
  "新竹縣",
  "苗栗縣",
  "臺中市",
  "彰化縣",
  "南投縣",
  "雲林縣",
  "嘉義市",
  "嘉義縣",
  "臺南市",
  "高雄市",
  "屏東縣",
  "台東縣",
  "花蓮縣",
  "宜蘭縣",
  "基隆市",
  "澎湖縣",
  "金門縣",
  "連江縣",
];

const BASEMAP = {
  id: "carto-voyager",
  name: "CARTO Voyager",
  url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
  subdomains: "abcd",
};

const map = L.map("map", {
  center: TAIWAN_CENTER,
  zoom: 8,
  minZoom: 7,
  maxZoom: 18,
  maxBounds: activeMaxBounds(),
  maxBoundsViscosity: 1,
  worldCopyJump: false,
  zoomControl: true,
  attributionControl: false,
  zoomDelta: ZOOM_BUTTON_STEP,
  zoomSnap: ZOOM_SNAP_STEP,
  scrollWheelZoom: true,
  wheelDebounceTime: 25,
  wheelPxPerZoomLevel: 160,
  zoomAnimation: true,
  fadeAnimation: true,
  markerZoomAnimation: true,
});

// 版本／圖資標示改放左上角一顆小圓標，避免壓在地圖與抽屜的接縫中間
L.control.attribution({ position: "topleft", prefix: false }).addTo(map);

function updateMinZoomForBounds() {
  const minZoom = Math.max(7, map.getBoundsZoom(activeMaxBounds(), true));
  map.setMinZoom(minZoom);
  if (map.getZoom() < minZoom) {
    map.setZoom(minZoom, { animate: false });
  }
}

// 手機／桌機切換時，套用對應的地圖可視範圍
function applyMaxBounds() {
  map.setMaxBounds(activeMaxBounds());
  updateMinZoomForBounds();
}

const markerLayer = L.layerGroup().addTo(map);
const summaryText = document.querySelector("#summaryText");
const movieSelect = document.querySelector("#movieSelect");
const searchInput = document.querySelector("#searchInput");
const chainFilterList = document.querySelector("#chainFilterList");
const cityFilterList = document.querySelector("#cityFilterList");
const clearSearchButton = document.querySelector("#clearSearchButton");
const searchSuggestions = document.querySelector("#searchSuggestions");
const resetViewButton = document.querySelector("#resetViewButton");
const dateChips = document.querySelector("#dateChips");

const {
  formatMinutes,
  manualTimeReached,
  showtimePassesTimeState,
  snapManualMinutes,
  taipeiNowMinutes,
} = window.MuseTimeFilter;
const {
  availableDatesForMovie,
  dateChipLabel,
  selectedDateForMovie,
  summaryTextForDate,
  taipeiToday,
} = window.MuseDateState;

let features = [];
let movieSummaries = [];
let movieFeaturesByTitle = new Map();
let movieFeaturesByTitleAndDate = new Map();
let selectedMovieTitle = "";
let availableDates = [];
let selectedDate = taipeiToday();
let dataUpdatedAt = "";
let chainLogoByName = new Map();
let markerById = new Map();
let activeId = null;
let selectedChain = "";
let selectedCity = "";

// 手機與桌機共用同一份時間狀態。AUTO 跟隨台灣現在時間；MANUAL 保存使用者
// 選擇的 15 分鐘級距。現在時間另存，避免混淆 > now 與 >= manual 的邊界。
let timeMode = "auto";
let taipeiCurrentMinute = taipeiNowMinutes();
let timeEarliest = taipeiCurrentMinute;
let timePeriod = "all"; // 快速時段
const PERIOD_RANGES = {
  all: [0, 1440],
  morning: [0, 720], // 上午（中午前）
  afternoon: [720, 1080], // 下午（12:00–18:00）
  evening: [1080, 1440], // 晚上（18:00 後）
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeSearchText(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replaceAll("臺", "台");
}

function markerClass(chainName) {
  if (/威秀|MUVIE/.test(chainName)) return "marker-blue";
  if (/國賓|秀泰|新光/.test(chainName)) return "marker-red";
  if (/in89|喜樂|美麗新/.test(chainName)) return "marker-yellow";
  return "";
}

function markerLabel(chainName) {
  const normalized = chainName.replace("影城", "").replace("CINEMAS", "").trim();
  return normalized.slice(0, 1).toUpperCase();
}

function markerLogo(chainName) {
  return chainLogoByName.get(chainName) || "";
}

function showtimeCount(feature) {
  const props = feature.properties;
  const count = Number(props.showtime_count);
  if (Number.isFinite(count) && count > 0) return count;
  return Array.isArray(props.showtimes) ? props.showtimes.length : 0;
}

// 回傳目前時間條件下真正會顯示的場次。Logo 徽章、Logo 大小、搜尋候選、
// 場次資訊卡共用這個來源，避免各處顯示不同的數字。
function showtimeMatchesTimeFilter(showtime) {
  const minutes = showtimeMinutes(showtime);
  return showtimePassesTimeState(
    minutes,
    {
      nowMinutes: selectedDate === taipeiToday() ? taipeiCurrentMinute : -1,
      mode: timeMode,
      manualEarliest: timeEarliest,
      period: timePeriod,
    },
    PERIOD_RANGES,
  );
}

function visibleShowtimes(feature) {
  const list = Array.isArray(feature.properties.showtimes) ? feature.properties.showtimes : [];
  return list.filter(showtimeMatchesTimeFilter);
}

function visibleShowtimeCount(feature) {
  return visibleShowtimes(feature).length;
}

function markerSize(feature) {
  const count = visibleShowtimeCount(feature);
  if (count <= 0) return MIN_MARKER_SIZE;
  return Math.round(clamp(MIN_MARKER_SIZE + Math.sqrt(count) * 4.5, MIN_MARKER_SIZE, MAX_MARKER_SIZE));
}

function markerZIndexOffset(feature) {
  return (MAX_MARKER_SIZE - markerSize(feature)) * 1000;
}

// 浮起圓牌 pin（設計四）：圓牌 logo 面浮在上方，細桿連到地面小點，錨點在地面點
function createIcon(feature) {
  const props = feature.properties;
  const size = markerSize(feature);
  const count = visibleShowtimeCount(feature);
  const fontSize = Math.round(clamp(size * 0.38, 11, 16));
  const stem = Math.max(6, Math.round(size * 0.24));
  const groundHeight = 4;
  const totalHeight = size + stem + groundHeight;
  const logoUrl = markerLogo(props.chain_name);
  const markerContent = logoUrl ? "" : escapeHtml(markerLabel(props.chain_name));
  const logoClass = logoUrl ? "has-logo" : "";
  const logoStyle = logoUrl ? ` --marker-logo: url('${escapeHtml(logoUrl)}');` : "";
  return L.divIcon({
    className: "",
    html: `<span class="cinema-pin" style="--marker-size: ${size}px; --pin-stem: ${stem}px;"><span class="cinema-marker ${markerClass(
      props.chain_name,
    )} ${logoClass}" aria-label="${escapeHtml(
      props.chain_name,
    )}，${escapeHtml(dateChipLabel(selectedDate))} ${count} 場" style="--marker-font-size: ${fontSize}px;${logoStyle}">${markerContent}</span><span class="cinema-showtime-count" aria-hidden="true">${count}</span><span class="pin-stem"></span><span class="pin-ground"></span></span>`,
    iconSize: [size, totalHeight],
    iconAnchor: [size / 2, totalHeight - Math.round(groundHeight / 2)],
    popupAnchor: [0, -totalHeight + 2],
  });
}

const PIN_SVG =
  '<svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" focusable="false">' +
  '<path fill="currentColor" d="M12 2a7 7 0 0 0-7 7c0 5.05 6.16 12.24 6.42 12.55a.75.75 0 0 0 1.16 0C12.84 21.24 19 14.05 19 9a7 7 0 0 0-7-7Zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5Z"/></svg>';

// 搜尋候選右側「跳到地圖」的往右上箭頭
const ARROW_SVG =
  '<svg class="suggestion-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M7 17L17 7M17 7H8M17 7v9"/></svg>';

// 資訊卡：日期／場次入口／官方網站的小圖示
const CAL_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<rect x="3" y="4.5" width="18" height="16" rx="2.5"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/></svg>';
const TICKET_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M4 7.5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1V10a2 2 0 0 0 0 4v2.5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V14a2 2 0 0 0 0-4Z"/><path d="M15 6.5v11" stroke-dasharray="2 2"/></svg>';
const GLOBE_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 2.7 2.6 15.3 0 18M12 3c-2.6 2.7-2.6 15.3 0 18"/></svg>';

function mapsUrl(feature) {
  const props = feature.properties || {};
  const name = props.location_name || props.map_name || "";
  if (!name) return "";
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(name)}`;
}

function showtimeSubLabel(showtime) {
  const label = showtime.label || "";
  const rest = showtime.time ? label.replace(showtime.time, "").trim() : label;
  return rest || showtime.format || "";
}

// 各家影城的場次補充字格式南轅北轍（含廳號、座位數、樓層、片名、分級…），
// 只用白名單擷取「版本（規格）＋語言」，其餘一律捨去。
// 例：「(數位 英)玩具總動員5 (普遍級)」→「數位 英語」、「數位 國語 / 3廳」→「數位 國語」、
//     「05廳(6樓)」→「」、「(GC 數位 英)…」→「GC 數位 英語」。
const FORMAT_RULES = [
  ["IMAX", /imax/i],
  ["4DX", /4dx/i],
  ["MX4D", /mx-?4d/i],
  ["ScreenX", /screen\s*-?\s*x/i],
  ["巨幕", /巨幕/],
  ["TITAN", /titan/i],
  ["ULTRA", /ultra/i],
  ["LUXE", /luxe/i],
  ["Dolby", /dolby|\bdva\b/i],
  ["ATMOS", /atmos/i],
  ["GC", /\bgc\b|gold\s*class/i],
  ["MUCROWN", /mucrown/i],
  ["A+", /a\+/i],
  ["皇家廳", /皇家廳/],
  ["COACH廳", /coach廳/i],
  ["BOOM廳", /boom廳/i],
  ["Pink Sofa", /pink\s*sofa/i],
  ["VIP", /\bvip\b/i],
  ["3D", /3d/i],
  ["數位", /數位/],
  ["2D", /2d/i],
];

const LANG_RULES = [
  ["日語", /日語|日文|JPN|[（(]\s*日\s*[)）]/i],
  ["英語", /英語|英文|ENG|[（(]\s*英\s*[)）]/i],
  ["國語", /國語|中文|CHT|[（(]\s*中\s*[)）]/i],
  ["台語", /台語|臺語/],
  ["粵語", /粵語/],
];

function showtimeTag(showtime) {
  const raw = showtimeSubLabel(showtime);
  if (!raw) return "";

  const formats = [];
  for (const [name, re] of FORMAT_RULES) {
    if (re.test(raw) && !formats.includes(name)) formats.push(name);
  }
  // 同義／重複去除：數位＝2D 只留數位；DolbyVisionAtmos 已含 Dolby，去掉 ATMOS
  if (formats.includes("數位")) {
    const i = formats.indexOf("2D");
    if (i !== -1) formats.splice(i, 1);
  }
  if (formats.includes("Dolby")) {
    const i = formats.indexOf("ATMOS");
    if (i !== -1) formats.splice(i, 1);
  }

  let lang = "";
  for (const [name, re] of LANG_RULES) {
    if (re.test(raw)) {
      lang = name;
      break;
    }
  }
  // 語言 fallback：只看第一個括號內的單字（避免掃到片名而誤判）
  if (!lang) {
    const paren = /[（(]([^（()）]*)[)）]/.exec(raw);
    const inside = paren ? paren[1] : "";
    if (/日/.test(inside)) lang = "日語";
    else if (/英/.test(inside)) lang = "英語";
    else if (/[國中]/.test(inside)) lang = "國語";
    else if (/台/.test(inside)) lang = "台語";
  }

  return [...formats.slice(0, 2), lang].filter(Boolean).join(" ");
}

// 保險機制：白名單是「認得才留」，若日後資料出現沒收錄的新規格關鍵字會被靜默丟掉。
// 這裡在載入後掃一遍，把「算不出任何版本／語言、但看起來可能藏著新規格」的補充字
// 收集起來提醒（全大寫拉丁字串通常就是規格品牌，如 IMAX／SCREENX／未知的 XLAND…），
// 方便你發現後補進 FORMAT_RULES；純廳號、純片名不會誤報。
const AUDIT_IGNORE_CAPS = new Set(["ENG", "JPN", "CHT"]);
function suspiciousSpecTokens(rawLabel, tag) {
  if (tag) return []; // 已擷取到版本／語言就沒問題
  const cleaned = rawLabel.replace(/[（(][^（()）]*[)）]/g, " "); // 去掉括號內附註（分級／英文片名）
  const caps = cleaned.match(/[A-Z][A-Z.+-]{2,}/g) || []; // 全大寫拉丁 ≥3
  return caps.filter((word) => !AUDIT_IGNORE_CAPS.has(word.replace(/[.+-]/g, "").toUpperCase()));
}

function auditShowtimeSpecs() {
  const flagged = new Map(); // 原文 -> 可疑 token
  for (const list of movieFeaturesByTitle.values()) {
    for (const feature of list) {
      for (const showtime of feature.properties.showtimes || []) {
        const raw = showtimeSubLabel(showtime);
        if (!raw || flagged.has(raw)) continue;
        const tokens = suspiciousSpecTokens(raw, showtimeTag(showtime));
        if (tokens.length) flagged.set(raw, tokens);
      }
    }
  }
  if (flagged.size) {
    console.warn(
      `[場次規格白名單] 有 ${flagged.size} 種補充字可能含未收錄的版本／規格，` +
        `確認後可補進 app.js 的 FORMAT_RULES：\n` +
        [...flagged].map(([raw, tokens]) => `  • ${raw}   → 可疑: ${tokens.join(", ")}`).join("\n"),
    );
  }
}

function popupHtml(feature) {
  const props = feature.properties;
  const gmap = mapsUrl(feature);
  const pin = gmap
    ? `<a class="popup-pin" href="${escapeHtml(gmap)}" target="_blank" rel="noreferrer" title="在 Google 地圖開啟" aria-label="在 Google 地圖開啟">${PIN_SVG}</a>`
    : "";
  const address = props.address
    ? `<p class="popup-address"><span>${escapeHtml(props.address)}</span>${pin}</p>`
    : "";
  const dateText = props.show_date
    ? escapeHtml(props.show_date).replaceAll("-", "/")
    : "當日場次";
  const showtimes = visibleShowtimes(feature);
  const showtimeBlock = showtimes.length
    ? `
        <div class="popup-showtimes">
          <div class="popup-showtimes-head">
            <span class="pst-date">${CAL_SVG}${dateText}</span>
            <span class="pst-count">${showtimes.length} 場</span>
          </div>
          <div class="showtime-grid">${showtimes
            .map((showtime) => {
              const tag = showtimeTag(showtime);
              return `<span class="st-chip"><b>${escapeHtml(showtime.time || "")}</b>${
                tag ? `<small>${escapeHtml(tag)}</small>` : ""
              }</span>`;
            })
            .join("")}</div>
        </div>
      `
    : "";
  const unavailableMessage = props.showtime_unavailable
    ? `<p class="popup-showtime-unavailable">${escapeHtml(
        props.showtime_unavailable_reason || "官方場次暫時無法取得，請前往場次入口查看。",
      )}</p>`
    : "";
  const locationLink = props.location_url
    ? `<a class="popup-link popup-link-primary" href="${escapeHtml(props.location_url)}" target="_blank" rel="noreferrer">${TICKET_SVG}場次入口</a>`
    : "";
  const officialLink = props.official_url
    ? `<a class="popup-link popup-link-ghost" href="${escapeHtml(props.official_url)}" target="_blank" rel="noreferrer">${GLOBE_SVG}官方網站</a>`
    : "";
  // 方案一：品牌色帶頁首（標題＋地址反白）＋ 白底內容（場次膠囊＋連結）
  return `
    <div class="pop-head">
      <h2 class="popup-title">${escapeHtml(props.location_name)}</h2>
      ${address}
    </div>
    <div class="pop-body">
      ${showtimeBlock || unavailableMessage}
      <div class="popup-links">${locationLink}${officialLink}</div>
    </div>
  `;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function createTileLayer(basemap) {
  const options = {
    attribution: basemap.attribution,
    className: basemap.className || "",
    maxZoom: basemap.maxZoom || 18,
    noWrap: true,
  };
  if (basemap.subdomains) {
    options.subdomains = basemap.subdomains;
  }
  return L.tileLayer(basemap.url, options);
}

function countBy(featuresToCount, key) {
  const counts = new Map();
  for (const feature of featuresToCount) {
    const value = feature.properties[key];
    if (!value) continue;
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  return counts;
}

// 分面計數：套用「其他」所有篩選（帶入的 predicates）後再依 key 分組計數，
// 讓地區／影城的數字會隨彼此（以及搜尋、時間）的篩選連動變化。
function facetCounts(key, predicates) {
  const counts = new Map();
  for (const feature of features) {
    if (!predicates.every((predicate) => predicate(feature))) continue;
    const value = feature.properties[key];
    if (!value) continue;
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  return counts;
}

// 清單與排序固定用整部電影的品牌（順序不會因篩選而跳動），
// 顯示的數字則用「排除影城本身」的分面計數；數字為 0 者不顯示
//（已選取的仍保留，才能再點一下取消）。
function sortedChains() {
  const baseline = countBy(features, "chain_name");
  const counts = facetCounts("chain_name", [keywordMatch, cityMatch, passesTimeFilter]);
  return [...baseline.keys()]
    .map((name) => [name, counts.get(name) || 0])
    .filter(([name, count]) => count > 0 || name === selectedChain)
    .sort((a, b) => {
      const ac = baseline.get(a[0]);
      const bc = baseline.get(b[0]);
      if (bc !== ac) return bc - ac;
      return a[0].localeCompare(b[0], "zh-Hant");
    });
}

// 縣市固定用 CITY_ORDER 排序，數字用「排除縣市本身」的分面計數；
// 數字為 0 者不顯示（已選取的仍保留，才能再點一下取消）。
function sortedCities() {
  const baseline = countBy(features, "city");
  const counts = facetCounts("city", [keywordMatch, chainMatch, passesTimeFilter]);
  return [...baseline.keys()]
    .map((city) => [city, counts.get(city) || 0])
    .filter(([city, count]) => count > 0 || city === selectedCity)
    .sort((a, b) => {
      const aIndex = CITY_ORDER.indexOf(a[0]);
      const bIndex = CITY_ORDER.indexOf(b[0]);
      const safeA = aIndex === -1 ? 999 : aIndex;
      const safeB = bIndex === -1 ? 999 : bIndex;
      if (safeA !== safeB) return safeA - safeB;
      return a[0].localeCompare(b[0], "zh-Hant");
    });
}

// 以該縣市所有影城座標的中心點，把地圖飛到縣市層級
function flyToCity(city) {
  const pts = features.filter((feature) => feature.properties.city === city);
  if (!pts.length) return;
  let sumLat = 0;
  let sumLng = 0;
  for (const feature of pts) {
    const [lng, lat] = feature.geometry.coordinates;
    sumLat += lat;
    sumLng += lng;
  }
  map.flyTo([sumLat / pts.length, sumLng / pts.length], CITY_ZOOM, { duration: 0.5 });
}

function renderFilterButtons(container, items, selectedValue, onSelect) {
  const fragment = document.createDocumentFragment();
  for (const [value, count] of items) {
    const button = document.createElement("button");
    button.className = "filter-option";
    button.type = "button";
    button.classList.toggle("is-selected", value === selectedValue);
    button.innerHTML = `
      <span>${escapeHtml(value)}</span>
      <strong>${count}</strong>
    `;
    button.addEventListener("click", () => onSelect(value));
    fragment.appendChild(button);
  }
  container.replaceChildren(fragment);
}

function renderFilters() {
  renderFilterButtons(chainFilterList, sortedChains(), selectedChain, (value) => {
    selectedChain = selectedChain === value ? "" : value;
    applyFilters();
  });
  renderFilterButtons(cityFilterList, sortedCities(), selectedCity, (value) => {
    selectedCity = selectedCity === value ? "" : value;
    applyFilters();
    if (selectedCity) flyToCity(selectedCity);
  });
}

// 去掉名稱尾端的規格括號，例如「台北松仁 (MUCROWN)」→「台北松仁」
function locationGroupName(name) {
  return String(name ?? "")
    .replace(/\s*[（(][^（()）]*[)）]\s*$/, "")
    .trim();
}

function showtimeMinutes(showtime) {
  const match = /(\d{1,2}):(\d{2})/.exec(showtime.time || "");
  if (!match) return Number.MAX_SAFE_INTEGER;
  return Number(match[1]) * 60 + Number(match[2]);
}

// 同一據點（同座標）但不同規格廳（如一般廳與 MUCROWN）在來源被拆成多筆，
// 合併成一張資訊卡：沿用主要那筆的基本資料，場次接起來依時間排序。
// 場次文字本身已帶「數位／MUCROWN」等規格字樣，使用者可自行分辨。
function mergeFeatures(rawFeatures) {
  const groups = new Map();
  const order = [];
  for (const feature of rawFeatures) {
    const [lng, lat] = feature.geometry.coordinates;
    const key = `${feature.properties.chain_name}@${lng},${lat}`;
    if (!groups.has(key)) {
      groups.set(key, []);
      order.push(key);
    }
    groups.get(key).push(feature);
  }

  return order.map((key) => {
    const group = groups.get(key);
    if (group.length === 1) return group[0];
    // 以名稱最短者為主，通常即為不帶規格括號的一般廳
    const primary = group.reduce((a, b) =>
      (b.properties.location_name || "").length < (a.properties.location_name || "").length ? b : a,
    );
    const showtimes = group
      .flatMap((feature) => (Array.isArray(feature.properties.showtimes) ? feature.properties.showtimes : []))
      .slice()
      .sort((a, b) => showtimeMinutes(a) - showtimeMinutes(b));
    return {
      ...primary,
      properties: {
        ...primary.properties,
        location_name: locationGroupName(primary.properties.location_name),
        map_name: locationGroupName(primary.properties.map_name),
        showtimes,
        showtime_count: showtimes.length,
      },
    };
  });
}

function normalizeMovieData(data) {
  dataUpdatedAt = typeof data.updated_at === "string" ? data.updated_at : "";
  movieFeaturesByTitle = new Map();
  movieFeaturesByTitleAndDate = new Map();

  if (Array.isArray(data.movies) && data.movies.length && data.movie_features) {
    for (const movie of data.movies) {
      const title = movie.title;
      if (!title) continue;
      const byDate = new Map();
      const rawByDate = data.movie_features_by_date?.[title];
      if (rawByDate && typeof rawByDate === "object") {
        for (const [showDate, rawFeatures] of Object.entries(rawByDate)) {
          if (!Array.isArray(rawFeatures)) continue;
          byDate.set(showDate, mergeFeatures(rawFeatures));
        }
      } else {
        const showDate = movie.show_date || data.show_date || taipeiToday();
        const rawFeatures = Array.isArray(data.movie_features[title]) ? data.movie_features[title] : [];
        byDate.set(showDate, mergeFeatures(rawFeatures));
      }
      movieFeaturesByTitleAndDate.set(title, byDate);
    }
  } else {
    const title = data.movie_title || data.name || "目前資料";
    const showDate = data.show_date || taipeiToday();
    movieFeaturesByTitleAndDate.set(
      title,
      new Map([[showDate, mergeFeatures(Array.isArray(data.features) ? data.features : [])]]),
    );
  }

  const today = taipeiToday();
  selectedMovieTitle = movieFeaturesByTitleAndDate.keys().next().value || "";
  availableDates = availableDatesForMovie(movieFeaturesByTitleAndDate.get(selectedMovieTitle));
  selectedDate = selectedDateForMovie(data.show_date, availableDates, today);
  refreshMovieDateData();
}

function refreshMovieDateData() {
  movieSummaries = [];
  movieFeaturesByTitle = new Map();
  for (const [title, byDate] of movieFeaturesByTitleAndDate) {
    const movieFeatures = byDate.get(selectedDate) || [];
    const showtimeTotal = movieFeatures.reduce((sum, feature) => sum + showtimeCount(feature), 0);
    movieSummaries.push({
      title,
      showDate: selectedDate,
      featureCount: movieFeatures.length,
      showtimeTotal,
    });
    movieFeaturesByTitle.set(title, movieFeatures);
  }
  features = movieFeaturesByTitle.get(selectedMovieTitle) || [];
}

function renderDateChips() {
  const fragment = document.createDocumentFragment();
  for (const showDate of availableDates) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "date-chip";
    button.dataset.date = showDate;
    button.classList.toggle("is-selected", showDate === selectedDate);
    button.setAttribute("aria-pressed", showDate === selectedDate ? "true" : "false");
    button.textContent = dateChipLabel(showDate);
    fragment.appendChild(button);
  }
  dateChips.replaceChildren(fragment);
  dateChips.hidden = availableDates.length <= 1;
}

function selectDate(showDate) {
  if (!availableDates.includes(showDate) || showDate === selectedDate) return;
  if (window.trackEvent) window.trackEvent("select_show_date", { show_date: showDate });
  selectedDate = showDate;
  setQuickPeriod("all");
  setAutoTimeMode(false);
  refreshMovieDateData();
  renderDateChips();
  renderMovieOptions();
  applyFilters();
}

function renderMovieOptions() {
  const fragment = document.createDocumentFragment();
  for (const movie of movieSummaries) {
    const option = document.createElement("option");
    option.value = movie.title;
    option.textContent = `${movie.title} (${movie.featureCount})`;
    option.selected = movie.title === selectedMovieTitle;
    fragment.appendChild(option);
  }
  movieSelect.replaceChildren(fragment);
  movieSelect.disabled = movieSummaries.length <= 1;
  renderMobileMovies();
}

function selectMovie(movieTitle) {
  if (!movieFeaturesByTitleAndDate.has(movieTitle)) return;
  if (window.trackEvent) window.trackEvent("select_movie", { movie_title: movieTitle });
  selectedMovieTitle = movieTitle;
  availableDates = availableDatesForMovie(movieFeaturesByTitleAndDate.get(movieTitle));
  const nextDate = selectedDateForMovie(selectedDate, availableDates);
  if (nextDate !== selectedDate) {
    selectedDate = nextDate;
    setQuickPeriod("all");
    // refreshMovieDateData() 尚未切換 features；此處只更新時間 state，
    // 最後由本函式既有的 applyFilters() 統一 render，避免舊 features 閃現一次。
    setAutoTimeMode(false);
  }
  refreshMovieDateData();
  activeId = null;
  selectedChain = "";
  selectedCity = "";
  renderDateChips();
  renderMovieOptions();
  renderFilters();
  applyFilters();
}

// 時間篩選以單一場次為單位套用：同一場必須同時通過「最早場次」與
// 「快速時段」。如此 Logo 徽章的數字就是使用者點進去後實際看到的場次數。
function passesTimeFilter(feature) {
  return visibleShowtimeCount(feature) > 0;
}

// 拆成各自獨立的判斷式，方便分面計數時「排除自己這一項」重新計算
function keywordMatch(feature) {
  const keyword = normalizeSearchText(activeSearchInput().value);
  if (!keyword) return true;
  const props = feature.properties;
  const haystack = normalizeSearchText(
    [props.chain_name, props.location_name, props.map_name, props.address, props.city].join(" "),
  );
  return haystack.includes(keyword);
}

function chainMatch(feature) {
  return !selectedChain || feature.properties.chain_name === selectedChain;
}

function cityMatch(feature) {
  return !selectedCity || feature.properties.city === selectedCity;
}

function matchesFilters(feature) {
  return keywordMatch(feature) && chainMatch(feature) && cityMatch(feature) && passesTimeFilter(feature);
}

function setActive(id) {
  activeId = id;
  document.querySelectorAll(".suggestion-row").forEach((row) => {
    row.classList.toggle("is-active", Number(row.dataset.id) === id);
  });
}

const FOCUS_ZOOM = 14; // 點 logo 放大到的據點層級
const CITY_ZOOM = 11; // 再點一下縮回的縣市層級
let zoomedInId = null;
let activeDesktopPopupId = null;

// 放大聚焦某據點並開啟資訊卡片（搜尋清單與第一次點 logo 都走這條）
// 手機一律改開底部 sheet（含搜尋推薦），桌機維持 popup。
function focusFeature(feature) {
  if (isMobile()) {
    openMobileSheet(feature);
    return;
  }
  const props = feature.properties;
  const marker = markerById.get(props.location_id);
  if (!marker) return;
  setActive(props.location_id);
  zoomedInId = props.location_id;
  const zoom = Math.max(map.getZoom(), FOCUS_ZOOM);
  // 先開 popup（已關 autoPan，不會自行平移），待其排版完成後量出
  // 「popup 卡片中心 → logo 錨點」的像素位移（與縮放無關），
  // 直接把該卡片中心當成地圖新中心，一次 flyTo 到位（不再兩段跳動）。
  marker.openPopup();
  requestAnimationFrame(() => {
    const popupEl = marker.getPopup()?.getElement();
    const markerPoint = map.project(marker.getLatLng(), zoom);
    let targetPoint = markerPoint;
    if (popupEl) {
      // 統一換算成「地圖容器座標」再相減：popup 用視窗座標、latLngToContainerPoint
      // 用容器座標，桌機地圖被側欄往右推，兩者若不換算會差一個側欄寬度。
      const mapRect = map.getContainer().getBoundingClientRect();
      const rect = popupEl.getBoundingClientRect();
      const anchor = map.latLngToContainerPoint(marker.getLatLng());
      const offsetX = rect.left + rect.width / 2 - mapRect.left - anchor.x;
      const offsetY = rect.top + rect.height / 2 - mapRect.top - anchor.y;
      targetPoint = markerPoint.add([offsetX, offsetY]);
    }
    map.flyTo(map.unproject(targetPoint, zoom), zoom, { duration: 0.45 });
  });
}

// 點地圖上的 logo：已放大在同一據點時再點一下 → 縮回縣市層級；否則放大
function toggleFeatureZoom(feature) {
  const props = feature.properties;
  const marker = markerById.get(props.location_id);
  if (!marker) return;
  const zoomedHere = zoomedInId === props.location_id && map.getZoom() >= FOCUS_ZOOM - 0.5;
  if (zoomedHere) {
    zoomedInId = null;
    marker.closePopup();
    map.flyTo(marker.getLatLng(), CITY_ZOOM, { duration: 0.45 });
  } else {
    focusFeature(feature);
  }
}

function renderSearchSuggestions(filtered) {
  const input = activeSearchInput();
  const container = activeSuggestions();
  // 另一個（非作用中）容器清空收起，避免桌機／手機兩份候選同時殘留
  const other = container === searchSuggestions ? mSearchSuggestions : searchSuggestions;
  if (other) {
    other.replaceChildren();
    other.hidden = true;
  }

  const keyword = normalizeSearchText(input.value);
  if (!keyword) {
    container.replaceChildren();
    container.hidden = true;
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const feature of filtered) {
    const props = feature.properties;
    const button = document.createElement("button");
    button.className = "suggestion-row";
    button.type = "button";
    button.dataset.id = props.location_id;
    button.innerHTML = `
      <span class="suggestion-name">${escapeHtml(props.location_name)}</span>
      <span class="suggestion-count">${visibleShowtimeCount(feature)} 場</span>
      ${ARROW_SVG}
    `;
    button.addEventListener("click", () => {
      focusFeature(feature);
      container.hidden = true;
    });
    fragment.appendChild(button);
  }
  container.replaceChildren(fragment);
  container.hidden = filtered.length === 0;
  setActive(activeId);
}

function renderMarkers(filtered) {
  const desktopPopupIdToRestore = !isMobile() ? activeDesktopPopupId : null;
  // Leaflet 在 clearLayers() 時不保證同步移除 map 上已開啟的 popup。
  // 先明確關閉舊內容，再於 markers 重建後只恢復仍存在的同一影城，
  // 才能讓跨日內容刷新，並在下一日期無該影城時確實關閉。
  if (desktopPopupIdToRestore) map.closePopup();
  markerLayer.clearLayers();
  markerById = new Map();
  for (const feature of filtered) {
    const props = feature.properties;
    const [lng, lat] = feature.geometry.coordinates;
    const baseZIndexOffset = markerZIndexOffset(feature);
    const marker = L.marker([lat, lng], {
      icon: createIcon(feature),
      zIndexOffset: baseZIndexOffset,
      cinemaBaseZIndexOffset: baseZIndexOffset,
    });
    marker.bindPopup(popupHtml(feature), {
      className: "band-popup",
      // 網頁版固定卡片寬度（CSS 也以 !important 固定 320，比例 4:5）
      minWidth: 320,
      maxWidth: 320,
      // 關閉 autoPan：桌機改由 focusFeature 直接以「popup 卡片中心」為目標
      // 一次平移到位，不再先置中 logo 再 autoPan 兩段跳動。
      autoPan: false,
    });
    // 移除 Leaflet 綁定 popup 時自動加的「點擊即開 popup」handler：
    // 桌機改由 toggleFeatureZoom 明確開啟，手機則改開底部 sheet。
    // 若保留它，手機點 logo 時 popup 會自動開啟並 autoPan 平移地圖，
    // 蓋掉我們把 logo 置中的 setView，導致 logo 落到 sheet 後方。
    marker.off("click", marker._openPopup, marker);
    marker.on("popupopen", () => {
      activeDesktopPopupId = props.location_id;
    });
    marker.on("popupclose", () => {
      if (activeDesktopPopupId === props.location_id) activeDesktopPopupId = null;
    });
    marker.on("click", () => {
      if (window.trackEvent)
        window.trackEvent("select_cinema", {
          cinema: props.map_name || props.location_name || "",
          chain: props.chain_name || "",
          city: props.city || "",
          movie_title: selectedMovieTitle || "",
        });
      if (isMobile()) toggleMobileSheet(feature);
      else toggleFeatureZoom(feature);
    });
    marker.addTo(markerLayer);
    // Leaflet 的 divIcon 由 JavaScript 動態產生，因此 hover 狀態也在 marker
    // 建立後綁定；只允許有滑鼠 hover 能力的桌機觸發，避免觸控裝置黏住。
    const setMarkerHover = (hovered) => {
      if (isMobile() || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
      marker.getElement()?.querySelector(".cinema-marker")?.classList.toggle("is-hovered", hovered);
      marker.setZIndexOffset(hovered ? baseZIndexOffset + 100000 : baseZIndexOffset);
    };
    marker.on("mouseover", () => setMarkerHover(true));
    marker.on("mouseout", () => setMarkerHover(false));
    markerById.set(props.location_id, marker);
  }

  // 篩選會重建所有 Leaflet marker；若手機資訊 sheet 仍開著，重建後也要
  // 把目前影城的選取外觀套回去。若該影城已被篩掉，則一併收起 sheet。
  if (isMobile() && appShell.classList.contains("sheet-open")) {
    const selectedFeature = filtered.find((feature) => feature.properties.location_id === zoomedInId);
    if (selectedFeature && markerById.has(zoomedInId)) {
      const previousScrollTop = mSheetBody.scrollTop;
      mSheetBody.innerHTML = popupHtml(selectedFeature);
      mSheetBody.scrollTop = previousScrollTop;
      updateMobileMarkerSelection(zoomedInId);
    } else closeMobileSheet();
  } else if (desktopPopupIdToRestore && markerById.has(desktopPopupIdToRestore)) {
    markerById.get(desktopPopupIdToRestore).openPopup();
  }
}

function renderSummaryText(message = null) {
  const text = message ?? summaryTextForDate(selectedDate, dataUpdatedAt);
  summaryText.textContent = text;
  summaryText.hidden = !text;
}

function applyFilters() {
  // 先重繪地區／影城膠囊，讓分面數字隨當前所有篩選連動更新
  renderFilters();
  const filtered = features.filter(matchesFilters);
  renderMarkers(filtered);
  renderSearchSuggestions(filtered);
  renderSummaryText();
}

function resetView() {
  map.setView(TAIWAN_CENTER, 8, { animate: true });
}

function setQuickPeriod(period) {
  timePeriod = period;
  for (const child of timePeriodButtons.children) {
    child.classList.toggle("is-selected", child.dataset.period === period);
  }
}

function clearFiltersAndResetView() {
  selectedChain = "";
  selectedCity = "";
  searchInput.value = "";
  clearSearchButton.hidden = true;
  mSearchInput.value = "";
  mSearchClear.hidden = true;
  searchSuggestions.replaceChildren();
  searchSuggestions.hidden = true;
  mSearchSuggestions.replaceChildren();
  mSearchSuggestions.hidden = true;
  setQuickPeriod("all");
  setAutoTimeMode(false);
  map.closePopup();
  closeMobileSheet();
  activeId = null;
  zoomedInId = null;
  applyFilters();
  resetView();
}

async function loadLogos() {
  const response = await fetch(LOGO_URL, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Logo 對應表載入失敗：${response.status}`);
  }
  const data = await response.json();
  chainLogoByName = new Map(Object.entries(data));
}

async function loadData() {
  await loadLogos().catch((error) => {
    console.warn(error);
    chainLogoByName = new Map();
  });

  const response = await fetch(DATA_URL, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`GeoJSON 載入失敗：${response.status}`);
  }
  const data = await response.json();
  normalizeMovieData(data);
  auditShowtimeSpecs();
  renderDateChips();
  renderMovieOptions();
  renderFilters();
  applyFilters();
}

movieSelect.addEventListener("change", () => selectMovie(movieSelect.value));
dateChips.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-date]");
  if (button) selectDate(button.dataset.date);
});
searchInput.addEventListener("input", () => {
  clearSearchButton.hidden = !searchInput.value;
  applyFilters();
});
clearSearchButton.addEventListener("click", () => {
  searchInput.value = "";
  clearSearchButton.hidden = true;
  applyFilters();
  searchInput.focus();
});
resetViewButton.addEventListener("click", clearFiltersAndResetView);
map.on("resize", updateMinZoomForBounds);

/* ============================================================
   共用時間篩選＋手機版分段控制、上方搜尋與固定 4:6 底盤
   底盤高度由 CSS 固定成 40dvh（地圖 60 / 底盤 4），不可拖曳調整；
   手機各分頁內容在固定高度內各自捲動。
   ============================================================ */
const appShell = document.querySelector(".app-shell");
const mobileQuery = window.matchMedia("(max-width: 760px)");

// 手機分段控制與電影清單
const mSeg = document.querySelector("#mSeg");
const mMovieList = document.querySelector("#mMovieList");
// 手機與桌機共用的時間面板元件
const timeSlider = document.querySelector("#timeSlider");
const timeSliderTrack = timeSlider.querySelector(".m-track");
const timeSliderFill = document.querySelector("#timeSliderFill");
const timeSliderKnob = document.querySelector("#timeSliderKnob");
const timeFilterCaption = document.querySelector("#timeFilterCaption");
const timePeriodButtons = document.querySelector("#timePeriodButtons");
// 浮動搜尋與首頁控制在手機、桌機都會顯示
const mSearchInput = document.querySelector("#mSearchInput");
const mSearchClear = document.querySelector("#mSearchClear");
const mSearchSuggestions = document.querySelector("#mSearchSuggestions");
const mHome = document.querySelector("#mHome");

// 手機影城資訊底部 sheet（點 logo 開啟，佔 70dvh，地圖留 30dvh）
const mSheet = document.querySelector("#mSheet");
const mSheetBody = document.querySelector("#mSheetBody");
const mSheetClose = document.querySelector("#mSheetClose");

let mTab = "movie";

function isMobile() {
  return mobileQuery.matches;
}

// 搜尋改為統一使用浮在地圖上方的搜尋列（手機與桌機皆是），
// 側欄內原本的搜尋欄位改藏，位置讓給時間篩選。
function activeSearchInput() {
  return mSearchInput;
}

function activeSuggestions() {
  return mSearchSuggestions;
}

// 底盤高度固定（CSS 40dvh）；換頁／旋轉時讓 Leaflet 依可視區重繪
function refreshSheetLayout() {
  if (isMobile()) map.invalidateSize({ animate: false });
}

/* ---- 手機影城資訊底部 sheet ---- */
// sheet 開啟時地圖仍是滿版，只是下方 70% 被 sheet 蓋住，可視帶＝上方 30%
const MAP_STRIP_RATIO = 0.3;

// 手機點選影城後，讓唯一的作用中 Logo 維持放大並浮到最上層；關閉 sheet、
// 點地圖空白處或改選其他影城時，舊 Logo 會在同一處恢復原始大小與圖層。
function updateMobileMarkerSelection(selectedId = null) {
  for (const [id, marker] of markerById) {
    const selected = isMobile() && selectedId !== null && id === selectedId;
    const markerElement = marker.getElement()?.querySelector(".cinema-marker");
    markerElement?.classList.toggle("is-mobile-selected", selected);
    if (markerElement) markerElement.setAttribute("aria-current", selected ? "true" : "false");

    const baseZIndexOffset = marker.options.cinemaBaseZIndexOffset ?? marker.options.zIndexOffset ?? 0;
    marker.setZIndexOffset(selected ? baseZIndexOffset + 200000 : baseZIndexOffset);
  }
}

function openMobileSheet(feature) {
  const id = feature.properties.location_id;
  const marker = markerById.get(id);
  if (!marker) return;
  setActive(id);
  zoomedInId = id;
  updateMobileMarkerSelection(id);
  mSheetBody.innerHTML = popupHtml(feature);
  mSheetBody.scrollTop = 0;
  appShell.classList.add("sheet-open");
  mSheet.setAttribute("aria-hidden", "false");
  // 把該影城 logo 平移到可視帶（上方 30%）的中央：可視帶中心在畫面 15% 處，
  // 地圖幾何中心固定在 50%，因此中心需落在 logo 下方 (0.5 − 0.15)·高度 的位置。
  // 地圖維持滿版、不做 resize，避免 invalidateSize／maxBounds 回彈造成的偏移。
  const zoom = Math.max(map.getZoom(), FOCUS_ZOOM);
  const size = map.getSize();
  const targetPoint = map.project(marker.getLatLng(), zoom);
  const center = map.unproject(targetPoint.add([0, (0.5 - MAP_STRIP_RATIO / 2) * size.y]), zoom);
  map.setView(center, zoom, { animate: true, duration: 0.4 });
}

function closeMobileSheet() {
  appShell.classList.remove("sheet-open");
  mSheet.setAttribute("aria-hidden", "true");
  zoomedInId = null;
  updateMobileMarkerSelection();
}

// 再次點同一個 logo → sheet 往下收起、地圖縮回縣市層級；點別的 logo → 換該影城並保持開啟
function toggleMobileSheet(feature) {
  const id = feature.properties.location_id;
  if (appShell.classList.contains("sheet-open") && zoomedInId === id) {
    const marker = markerById.get(id);
    closeMobileSheet();
    if (marker) map.flyTo(marker.getLatLng(), CITY_ZOOM, { duration: 0.45 });
  } else {
    openMobileSheet(feature);
  }
}

mSheetClose.addEventListener("click", closeMobileSheet);
// 點地圖空白處（非 logo）收起 sheet
map.on("click", () => {
  if (isMobile()) closeMobileSheet();
});

/* ---- 分段控制：電影／地區／時間／影城 ---- */
function setMobileTab(tab) {
  mTab = tab;
  for (const button of mSeg.children) {
    button.classList.toggle("is-active", button.dataset.tab === tab);
  }
  appShell.classList.remove("mtab-movie", "mtab-city", "mtab-time", "mtab-chain");
  appShell.classList.add(`mtab-${tab}`);
}

mSeg.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-tab]");
  if (!button) return;
  setMobileTab(button.dataset.tab);
});

/* ---- 手機電影清單（片名＋場次，單選） ---- */
function renderMobileMovies() {
  const fragment = document.createDocumentFragment();
  for (const movie of movieSummaries) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "m-movie-row";
    button.classList.toggle("is-selected", movie.title === selectedMovieTitle);
    button.innerHTML = `
      <span class="mm-name">${escapeHtml(movie.title)}</span>
      <span class="mm-count">${movie.showtimeTotal} 場</span>
      <span class="mm-radio" aria-hidden="true"></span>
    `;
    button.addEventListener("click", () => selectMovie(movie.title));
    fragment.appendChild(button);
  }
  mMovieList.replaceChildren(fragment);
}

/* ---- 手機／桌機共用時間軸 ---- */
function renderTimeControls() {
  const isToday = selectedDate === taipeiToday();
  const displayedMinute = timeMode === "manual" ? timeEarliest : isToday ? taipeiCurrentMinute : 0;
  const frac = displayedMinute / 1440;
  timeSliderFill.style.width = `${frac * 100}%`;
  timeSliderKnob.style.left = `${frac * 100}%`;
  timeSliderKnob.textContent = formatMinutes(displayedMinute);
  timeFilterCaption.textContent = timeMode === "manual"
    ? `${formatMinutes(timeEarliest)} 起`
    : isToday
      ? `${formatMinutes(taipeiCurrentMinute)} 後`
      : "全天";
}

function setAutoTimeMode(apply = true) {
  taipeiCurrentMinute = taipeiNowMinutes();
  timeMode = "auto";
  timeEarliest = selectedDate === taipeiToday() ? taipeiCurrentMinute : 0;
  renderTimeControls();
  if (apply) applyFilters();
}

function setManualEarliest(minutes, apply = true) {
  taipeiCurrentMinute = taipeiNowMinutes();
  const snappedMinute = snapManualMinutes(minutes);
  if (selectedDate === taipeiToday() && snappedMinute <= taipeiCurrentMinute) {
    setAutoTimeMode(apply);
    return;
  }
  timeMode = "manual";
  timeEarliest = snappedMinute;
  renderTimeControls();
  if (apply) applyFilters();
}

function refreshCurrentTime(apply = true) {
  const nextMinute = taipeiNowMinutes();
  const minuteChanged = nextMinute !== taipeiCurrentMinute;
  taipeiCurrentMinute = nextMinute;
  if (selectedDate !== taipeiToday()) {
    renderTimeControls();
    return;
  }
  if (timeMode === "manual" && manualTimeReached(taipeiCurrentMinute, timeEarliest)) {
    timeMode = "auto";
    timeEarliest = taipeiCurrentMinute;
  } else if (timeMode === "auto") {
    timeEarliest = taipeiCurrentMinute;
  }
  renderTimeControls();
  if (apply && minuteChanged) applyFilters();
}

let minuteTimerId = null;

function scheduleMinuteBoundaryUpdate() {
  window.clearTimeout(minuteTimerId);
  const delay = 60000 - (Date.now() % 60000) + 25;
  minuteTimerId = window.setTimeout(() => {
    refreshCurrentTime();
    scheduleMinuteBoundaryUpdate();
  }, delay);
}

let sliderDragging = false;

function sliderFromClientX(clientX) {
  const rect = timeSliderTrack.getBoundingClientRect();
  if (!rect.width) return;
  const frac = clamp((clientX - rect.left) / rect.width, 0, 1);
  setManualEarliest(frac * 1440);
}

timeSliderKnob.addEventListener("pointerdown", (event) => {
  sliderDragging = true;
  timeSliderKnob.setPointerCapture?.(event.pointerId);
});
timeSliderKnob.addEventListener("pointermove", (event) => {
  if (sliderDragging) sliderFromClientX(event.clientX);
});
timeSliderKnob.addEventListener("pointerup", (event) => {
  sliderDragging = false;
  timeSliderKnob.releasePointerCapture?.(event.pointerId);
});
timeSliderKnob.addEventListener("pointercancel", () => {
  sliderDragging = false;
});
timeSlider.addEventListener("pointerdown", (event) => {
  if (event.target === timeSliderKnob) return;
  sliderFromClientX(event.clientX);
});

/* ---- 快速時段 ---- */
timePeriodButtons.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-period]");
  if (!button) return;
  setQuickPeriod(button.dataset.period);
  applyFilters();
});

/* ---- 手機搜尋（浮在地圖上方） ---- */
mSearchInput.addEventListener("input", () => {
  mSearchClear.hidden = !mSearchInput.value;
  applyFilters();
});
mSearchClear.addEventListener("click", () => {
  mSearchInput.value = "";
  mSearchClear.hidden = true;
  applyFilters();
  mSearchInput.focus();
});
mHome.addEventListener("click", () => {
  clearFiltersAndResetView();
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    refreshCurrentTime();
    scheduleMinuteBoundaryUpdate();
  }
});

window.addEventListener("resize", () => {
  refreshSheetLayout();
  map.invalidateSize({ animate: false });
  updateMinZoomForBounds();
});

// 切換手機／桌機時重繪，並套用對應的地圖可視範圍（手機南端多留白）
mobileQuery.addEventListener("change", () => {
  if (!isMobile()) closeMobileSheet();
  map.invalidateSize({ animate: false });
  applyMaxBounds();
});

updateMinZoomForBounds();
createTileLayer(BASEMAP).addTo(map).bringToBack();
setMobileTab("movie");
setAutoTimeMode(false);
scheduleMinuteBoundaryUpdate();
refreshSheetLayout();

loadData()
  .then(refreshSheetLayout)
  .catch((error) => {
    renderSummaryText(error.message);
    console.error(error);
  });
