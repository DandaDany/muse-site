const TAIWAN_CENTER = [23.75, 121.0];
const TAIWAN_BOUNDS = L.latLngBounds([21.5, 117.7], [26.6, 123.2]);
const DATA_URL = "data/locations.geojson";
const LOGO_URL = "data/chain_logos.json";
const ZOOM_BUTTON_STEP = 0.5;
const ZOOM_SNAP_STEP = 0.25;
const MIN_MARKER_SIZE = 24;
const MAX_MARKER_SIZE = 48;
const CITY_ORDER = [
  "台北市",
  "新北市",
  "桃園市",
  "新竹市",
  "新竹縣",
  "苗栗縣",
  "台中市",
  "彰化縣",
  "南投縣",
  "雲林縣",
  "嘉義市",
  "嘉義縣",
  "台南市",
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
  maxBounds: TAIWAN_BOUNDS,
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
  const minZoom = Math.max(7, map.getBoundsZoom(TAIWAN_BOUNDS, true));
  map.setMinZoom(minZoom);
  if (map.getZoom() < minZoom) {
    map.setZoom(minZoom, { animate: false });
  }
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

let features = [];
let movieSummaries = [];
let movieFeaturesByTitle = new Map();
let selectedMovieTitle = "";
let chainLogoByName = new Map();
let markerById = new Map();
let activeId = null;
let selectedChain = "";
let selectedCity = "";

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

function markerSize(feature) {
  const count = showtimeCount(feature);
  if (count <= 0) return MIN_MARKER_SIZE;
  return Math.round(clamp(MIN_MARKER_SIZE + Math.sqrt(count) * 4.5, MIN_MARKER_SIZE, MAX_MARKER_SIZE));
}

function markerZIndexOffset(feature) {
  return (MAX_MARKER_SIZE - markerSize(feature)) * 1000;
}

function createIcon(feature) {
  const props = feature.properties;
  const size = markerSize(feature);
  const fontSize = Math.round(clamp(size * 0.38, 11, 16));
  const logoUrl = markerLogo(props.chain_name);
  const markerContent = logoUrl ? "" : escapeHtml(markerLabel(props.chain_name));
  const logoClass = logoUrl ? "has-logo" : "";
  const logoStyle = logoUrl ? ` --marker-logo: url('${escapeHtml(logoUrl)}');` : "";
  return L.divIcon({
    className: "",
    html: `<span class="cinema-marker ${markerClass(
      props.chain_name,
    )} ${logoClass}" aria-label="${escapeHtml(
      props.chain_name,
    )}" style="--marker-size: ${size}px; --marker-font-size: ${fontSize}px;${logoStyle}">${markerContent}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -Math.round(size / 2)],
  });
}

const PIN_SVG =
  '<svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" focusable="false">' +
  '<path fill="currentColor" d="M12 2a7 7 0 0 0-7 7c0 5.05 6.16 12.24 6.42 12.55a.75.75 0 0 0 1.16 0C12.84 21.24 19 14.05 19 9a7 7 0 0 0-7-7Zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5Z"/></svg>';

// 搜尋候選右側「跳到地圖」的往右上箭頭
const ARROW_SVG =
  '<svg class="suggestion-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M7 17L17 7M17 7H8M17 7v9"/></svg>';

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

function popupHtml(feature) {
  const props = feature.properties;
  const gmap = mapsUrl(feature);
  const pin = gmap
    ? `<a class="popup-pin" href="${escapeHtml(gmap)}" target="_blank" rel="noreferrer" title="在 Google 地圖開啟" aria-label="在 Google 地圖開啟">${PIN_SVG}</a>`
    : "";
  const address = props.address
    ? `<p class="popup-address"><span>${escapeHtml(props.address)}</span>${pin}</p>`
    : "";
  const dateText = props.show_date ? `當日, ${escapeHtml(props.show_date).replaceAll("-", "/")}` : "當日";
  const showtimeBlock =
    Array.isArray(props.showtimes) && props.showtimes.length
      ? `
        <div class="popup-showtimes">
          <p class="popup-showtimes-head">${dateText}</p>
          <ul class="showtime-list">${props.showtimes
            .map(
              (showtime) =>
                `<li><b>${escapeHtml(showtime.time || "")}</b><span>${escapeHtml(showtimeSubLabel(showtime))}</span></li>`,
            )
            .join("")}</ul>
        </div>
      `
      : "";
  const locationLink = props.location_url
    ? `<a href="${escapeHtml(props.location_url)}" target="_blank" rel="noreferrer">場次入口</a>`
    : "";
  const officialLink = props.official_url
    ? `<a href="${escapeHtml(props.official_url)}" target="_blank" rel="noreferrer">官方網站</a>`
    : "";
  return `
    <h2 class="popup-title">${escapeHtml(props.location_name)}</h2>
    ${address}
    ${showtimeBlock}
    <div class="popup-links">${locationLink}${officialLink}</div>
  `;
}

/* ---- 威秀影城（VIESHOW）專用資訊卡：電影票造型 popup ----
   幾何與樣式來自 design/popup-card-preview.html，只套用在威秀，
   讓其他影城維持原本的簡潔 popup 以便並排比較視覺。 */
function isVieshow(chainName) {
  return /威秀|VIESHOW/i.test(chainName || "");
}

// 取品牌短標放進卡片右上角色塊（例：「威秀影城 / VIESHOW」→「VIESHOW」）
function brandTag(chainName) {
  const parts = String(chainName || "")
    .split("/")
    .map((part) => part.trim());
  const latin = parts.find((part) => /[A-Za-z]/.test(part));
  return (latin || parts[0] || "")
    .replace(/影城|CINEMAS?/gi, "")
    .trim()
    .toUpperCase();
}

const VS_PIN =
  '<svg viewBox="0 0 24 32" fill="none"><path d="M12 31S22 19.6 22 11.5C22 5.15 17.52 1 12 1S2 5.15 2 11.5C2 19.6 12 31 12 31Z" fill="currentColor"/><circle cx="12" cy="11.5" r="3.4" fill="#1b211d"/></svg>';
const VS_TICKET =
  '<svg width="40" height="40" viewBox="0 0 24 24" fill="none"><path d="M4 8.5V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2.5a2.5 2.5 0 0 0 0 5V16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2.5a2.5 2.5 0 0 0 0-5Z" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/></svg>';
const VS_GLOBE =
  '<svg width="40" height="40" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2.1"/><path d="M3 12h18M12 3c2.25 2.45 3.25 5.45 3.25 9S14.25 18.55 12 21M12 3C9.75 5.45 8.75 8.45 8.75 12S9.75 18.55 12 21" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"/></svg>';
const VS_X =
  '<svg width="20" height="20" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M2 2l10 10M12 2L2 12"/></svg>';

function scheduleDetail(showtime) {
  const format = showtime.format || showtimeSubLabel(showtime) || "";
  return showtime.auditorium ? `${format} ／ ${showtime.auditorium}` : format;
}

function vieshowCardHtml(feature) {
  const props = feature.properties;
  const date = String(props.show_date || "").replaceAll("-", "/");
  const rows = (Array.isArray(props.showtimes) ? props.showtimes : [])
    .map(
      (showtime) =>
        `<div class="mrow"><span class="mtime">${escapeHtml(
          showtime.time || "",
        )}</span><span class="mdetail">${escapeHtml(scheduleDetail(showtime))}</span></div>`,
    )
    .join("");
  const entry = props.location_url ? escapeHtml(props.location_url) : "#";
  const site = props.official_url ? escapeHtml(props.official_url) : "#";
  const clipId = `vs-photo-${props.location_id}`;
  return `<div class="scale-wrap"><article class="movie-card">
      <div class="base-cream"></div>
      <svg class="geometry-svg" viewBox="0 0 854 836" preserveAspectRatio="none" aria-hidden="true">
        <defs><clipPath id="${clipId}"><polygon points="609,0 854,0 854,205 550,150"/></clipPath></defs>
        <polygon class="shape-white-main" points="270,250 854,225 854,745 410,745 270,690"/>
        <polygon class="shape-dark" points="0,0 609,0 550,150 0,228"/>
        <g clip-path="url(#${clipId})"><rect class="photo-fill" x="545" y="0" width="309" height="245"/>
          <text class="photo-label" x="790" y="135" text-anchor="end" font-size="26">${escapeHtml(
            brandTag(props.chain_name),
          )}</text></g>
        <polygon class="shape-orange-line" points="0,226 550,150 0,241"/>
      </svg>
      <button class="close-hit" type="button" aria-label="關閉">${VS_X}</button>
      <div class="hero-content">
        <h2 class="hero-title">${escapeHtml(props.location_name)}</h2>
        <div class="hero-address">${VS_PIN}<span>${escapeHtml(props.address || "")}</span></div>
      </div>
      <div class="date-panel"></div>
      <div class="date-content">
        <div class="date-label">當日,</div>
        <div class="date-value">${escapeHtml(date)}</div>
      </div>
      <section class="msched">${rows}</section>
      <div class="footer-green"></div>
      <div class="footer-white"></div>
      <a class="entry-button" href="${entry}" target="_blank" rel="noreferrer">${VS_TICKET}<span>場次入口</span><span class="arrow">→</span></a>
      <a class="site-button" href="${site}" target="_blank" rel="noreferrer">${VS_GLOBE}<span>官方網站</span><span class="arrow">→</span></a>
    </article></div>`;
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

function sortedChains() {
  const counts = countBy(features, "chain_name");
  return [...counts.entries()].sort((a, b) => {
    if (b[1] !== a[1]) return b[1] - a[1];
    return a[0].localeCompare(b[0], "zh-Hant");
  });
}

function sortedCities() {
  const counts = countBy(features, "city");
  return [...counts.entries()].sort((a, b) => {
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
    renderFilters();
    applyFilters();
  });
  renderFilterButtons(cityFilterList, sortedCities(), selectedCity, (value) => {
    selectedCity = selectedCity === value ? "" : value;
    renderFilters();
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
  movieSummaries = [];
  movieFeaturesByTitle = new Map();

  if (Array.isArray(data.movies) && data.movies.length && data.movie_features) {
    for (const movie of data.movies) {
      const title = movie.title;
      if (!title) continue;
      const rawFeatures = Array.isArray(data.movie_features[title]) ? data.movie_features[title] : [];
      const movieFeatures = mergeFeatures(rawFeatures);
      movieSummaries.push({
        title,
        showDate: movie.show_date || data.show_date || "",
        featureCount: movieFeatures.length,
      });
      movieFeaturesByTitle.set(title, movieFeatures);
    }
  } else {
    const title = data.movie_title || data.name || "目前資料";
    const fallbackFeatures = mergeFeatures(Array.isArray(data.features) ? data.features : []);
    movieSummaries.push({
      title,
      showDate: data.show_date || "",
      featureCount: fallbackFeatures.length,
    });
    movieFeaturesByTitle.set(title, fallbackFeatures);
  }

  selectedMovieTitle = movieSummaries[0]?.title || "";
  features = movieFeaturesByTitle.get(selectedMovieTitle) || [];
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
}

function selectMovie(movieTitle) {
  if (!movieFeaturesByTitle.has(movieTitle)) return;
  selectedMovieTitle = movieTitle;
  features = movieFeaturesByTitle.get(movieTitle) || [];
  activeId = null;
  selectedChain = "";
  selectedCity = "";
  renderMovieOptions();
  renderFilters();
  applyFilters();
}

function matchesFilters(feature) {
  const props = feature.properties;
  const keyword = normalizeSearchText(searchInput.value);
  const haystack = normalizeSearchText([
    props.chain_name,
    props.location_name,
    props.map_name,
    props.address,
    props.city,
  ]
    .join(" "));

  return (
    (!keyword || haystack.includes(keyword)) &&
    (!selectedChain || props.chain_name === selectedChain) &&
    (!selectedCity || props.city === selectedCity)
  );
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

// 放大聚焦某據點並開啟資訊卡片（搜尋清單與第一次點 logo 都走這條）
function focusFeature(feature) {
  const props = feature.properties;
  const marker = markerById.get(props.location_id);
  if (!marker) return;
  setActive(props.location_id);
  zoomedInId = props.location_id;
  map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), FOCUS_ZOOM), { duration: 0.45 });
  marker.openPopup();
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
  const keyword = normalizeSearchText(searchInput.value);
  if (!keyword) {
    searchSuggestions.replaceChildren();
    searchSuggestions.hidden = true;
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
      <span class="suggestion-count">${showtimeCount(feature)} 場</span>
      ${ARROW_SVG}
    `;
    button.addEventListener("click", () => {
      focusFeature(feature);
      searchSuggestions.hidden = true;
    });
    fragment.appendChild(button);
  }
  searchSuggestions.replaceChildren(fragment);
  searchSuggestions.hidden = filtered.length === 0;
  setActive(activeId);
}

function renderMarkers(filtered) {
  markerLayer.clearLayers();
  markerById = new Map();
  for (const feature of filtered) {
    const props = feature.properties;
    const [lng, lat] = feature.geometry.coordinates;
    const marker = L.marker([lat, lng], {
      icon: createIcon(feature),
      zIndexOffset: markerZIndexOffset(feature),
    });
    const useCard = isVieshow(props.chain_name);
    marker.bindPopup(
      useCard ? vieshowCardHtml(feature) : popupHtml(feature),
      useCard
        ? {
            className: "vs-popup",
            minWidth: 0,
            maxWidth: 460,
            autoPan: true,
            autoPanPadding: [18, 24],
            // keepInView 會在 maxBounds（viscosity:1）下與 autoPan 互相觸發、無限遞迴，
            // 這張卡較高更容易踩到；改成只在開啟時 autoPan 一次即可
            keepInView: false,
            closeButton: false,
          }
        : {
            minWidth: 240,
            maxWidth: 320,
            autoPan: true,
            autoPanPadding: [16, 16],
            keepInView: true,
          },
    );
    marker.on("click", () => toggleFeatureZoom(feature));
    marker.addTo(markerLayer);
    markerById.set(props.location_id, marker);
  }
}

function applyFilters() {
  const filtered = features.filter(matchesFilters);
  renderMarkers(filtered);
  renderSearchSuggestions(filtered);
  const totalShowtimes = filtered.reduce((sum, feature) => sum + showtimeCount(feature), 0);
  const moviePrefix = selectedMovieTitle ? `${selectedMovieTitle}：` : "";
  summaryText.textContent = `${moviePrefix}${filtered.length} 影城上映中，共 ${totalShowtimes} 場次`;
  if (!isDragging) refreshSheetLayout();
}

function resetView() {
  map.setView(TAIWAN_CENTER, 8, { animate: true });
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
  renderMovieOptions();
  renderFilters();
  applyFilters();
}

movieSelect.addEventListener("change", () => selectMovie(movieSelect.value));
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
resetViewButton.addEventListener("click", resetView);
map.on("resize", updateMinZoomForBounds);

// 威秀資訊卡自帶關閉鈕（已停用 Leaflet 預設關閉鈕），開卡時綁上關閉行為
map.on("popupopen", (event) => {
  const root = event.popup.getElement();
  const closeButton = root && root.querySelector(".close-hit");
  if (closeButton) {
    closeButton.addEventListener("click", () => map.closePopup(event.popup));
  }
});

/* ---- 手機版底部抽屜：可自由拖曳，貼齊「收起／一半／展開」三個位置 ---- */
const appShell = document.querySelector(".app-shell");
const sidebar = document.querySelector(".sidebar");
const grabber = document.querySelector(".grabber");
const panelHead = document.querySelector(".panel-head");
const searchField = document.querySelector("#searchField");
const mobileQuery = window.matchMedia("(max-width: 760px)");

const SHEET_HEIGHT_RATIO = 0.86; // 抽屜總高度佔螢幕高度的比例（展開時最上緣露出的地圖比例反之）
const DRAG_CLICK_THRESHOLD = 6; // 移動小於這個距離視為點擊，不是拖曳

let snapPoints = { full: 0, half: 0, peek: 0 };
let currentSnap = "peek";
let dragPointerId = null;
let dragStartY = 0;
let dragStartTranslate = 0;
let isDragging = false;

function isMobile() {
  return mobileQuery.matches;
}

function viewportHeight() {
  return window.visualViewport ? window.visualViewport.height : window.innerHeight;
}

function setTranslate(px, animate) {
  appShell.classList.toggle("sheet-dragging", !animate);
  sidebar.style.setProperty("--sheet-translate", `${px}px`);
}

// 依螢幕高度與「抓握條＋標題／電影／搜尋」實際內容高度，算出收起時該露出多少
function computeSnapPoints() {
  if (!isMobile()) return;
  const sheetHeight = Math.round(viewportHeight() * SHEET_HEIGHT_RATIO);
  sidebar.style.setProperty("--sheet-height", `${sheetHeight}px`);

  const paddingBottom = parseFloat(getComputedStyle(sidebar).paddingBottom) || 0;
  const contentHeight = searchField.offsetTop + searchField.offsetHeight;
  const peekVisible = clamp(contentHeight + paddingBottom, 160, sheetHeight - 40);

  const peek = sheetHeight - peekVisible;
  const half = clamp(sheetHeight * 0.45, 0, peek);
  snapPoints = { full: 0, half, peek };
}

function currentTranslate() {
  const raw = getComputedStyle(sidebar).getPropertyValue("--sheet-translate");
  const value = parseFloat(raw);
  return Number.isFinite(value) ? value : snapPoints[currentSnap];
}

function nearestSnapName(px) {
  let best = "peek";
  let bestDistance = Infinity;
  for (const [name, value] of Object.entries(snapPoints)) {
    const distance = Math.abs(value - px);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = name;
    }
  }
  return best;
}

function applySnap(name, animate = true) {
  currentSnap = name;
  appShell.classList.toggle("sheet-open", name !== "peek");
  setTranslate(snapPoints[name], animate);
}

function refreshSheetLayout() {
  if (!isMobile()) return;
  computeSnapPoints();
  setTranslate(snapPoints[currentSnap], false);
}

function onSheetPointerDown(event) {
  if (!isMobile()) return;
  if (event.target.closest("#resetViewButton")) return;
  isDragging = true;
  dragPointerId = event.pointerId;
  dragStartY = event.clientY;
  dragStartTranslate = currentTranslate();
  event.currentTarget.setPointerCapture?.(dragPointerId);
}

function onSheetPointerMove(event) {
  if (!isDragging || event.pointerId !== dragPointerId) return;
  const delta = event.clientY - dragStartY;
  const next = clamp(dragStartTranslate + delta, snapPoints.full, snapPoints.peek);
  setTranslate(next, false);
}

function onSheetPointerUp(event) {
  if (!isDragging || event.pointerId !== dragPointerId) return;
  isDragging = false;
  dragPointerId = null;
  const moved = Math.abs(event.clientY - dragStartY);
  if (moved < DRAG_CLICK_THRESHOLD) {
    // 幾乎沒移動＝視為點擊：在收起與一半之間切換
    applySnap(currentSnap === "peek" ? "half" : "peek");
    return;
  }
  applySnap(nearestSnapName(currentTranslate()));
}

grabber.addEventListener("pointerdown", onSheetPointerDown);
panelHead.addEventListener("pointerdown", onSheetPointerDown);
window.addEventListener("pointermove", onSheetPointerMove);
window.addEventListener("pointerup", onSheetPointerUp);
window.addEventListener("pointercancel", onSheetPointerUp);

// 聚焦搜尋或篩選內容時，至少展開到一半，避免鍵盤把內容蓋住
sidebar.addEventListener("focusin", () => {
  if (!isMobile() || currentSnap !== "peek") return;
  applySnap("half");
});

// 點地圖即收合，把版面還給地圖
map.on("click", () => {
  if (isMobile()) applySnap("peek");
});

window.addEventListener("resize", () => {
  refreshSheetLayout();
  map.invalidateSize({ animate: false });
  updateMinZoomForBounds();
});

// 切換手機／桌機時重置抽屜狀態
mobileQuery.addEventListener("change", () => {
  if (isMobile()) {
    currentSnap = "peek";
    refreshSheetLayout();
  } else {
    appShell.classList.remove("sheet-open", "sheet-dragging");
    sidebar.style.removeProperty("--sheet-translate");
    sidebar.style.removeProperty("--sheet-height");
  }
  map.invalidateSize({ animate: false });
  updateMinZoomForBounds();
});

updateMinZoomForBounds();
createTileLayer(BASEMAP).addTo(map).bringToBack();
refreshSheetLayout();

loadData()
  .then(refreshSheetLayout)
  .catch((error) => {
    summaryText.textContent = error.message;
    console.error(error);
  });
