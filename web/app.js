const TAIWAN_CENTER = [23.75, 121.0];
const TAIWAN_BOUNDS = L.latLngBounds([21.5, 117.7], [26.6, 123.2]);
const DATA_URL = "data/locations.geojson";
const LOGO_URL = "data/chain_logos.json";
const ZOOM_BUTTON_STEP = 0.25;
const ZOOM_SNAP_STEP = 0;
const WHEEL_ZOOM_SENSITIVITY = 0.00045;
const WHEEL_ZOOM_EASE = 0.18;
const WHEEL_ZOOM_STOP_THRESHOLD = 0.003;
const WHEEL_TARGET_RESET_MS = 220;
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

const BASEMAPS = [
  {
    id: "osm-muted",
    name: "OSM 淡化",
    note: "原版資訊量，海域線較淡",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    className: "osm-muted-tile",
  },
  {
    id: "osm-standard",
    name: "OSM 原色",
    note: "最接近原本樣子",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  },
  {
    id: "carto-voyager",
    name: "CARTO Voyager",
    note: "接近 Google，路網清楚",
    url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd",
  },
  {
    id: "carto-positron",
    name: "CARTO Positron",
    note: "乾淨淡色，干擾最少",
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd",
  },
  {
    id: "esri-street",
    name: "Esri 街道",
    note: "商用地圖感，標示密",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles &copy; Esri",
  },
  {
    id: "esri-topo",
    name: "Esri 地形",
    note: "山區地形較清楚",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles &copy; Esri",
  },
];

const map = L.map("map", {
  center: TAIWAN_CENTER,
  zoom: 8,
  minZoom: 7,
  maxZoom: 18,
  maxBounds: TAIWAN_BOUNDS,
  maxBoundsViscosity: 1,
  worldCopyJump: false,
  zoomControl: true,
  zoomDelta: ZOOM_BUTTON_STEP,
  zoomSnap: ZOOM_SNAP_STEP,
  scrollWheelZoom: false,
});

const markerLayer = L.layerGroup().addTo(map);
const summaryText = document.querySelector("#summaryText");
const visibleCount = document.querySelector("#visibleCount");
const totalCount = document.querySelector("#totalCount");
const movieSelect = document.querySelector("#movieSelect");
const searchInput = document.querySelector("#searchInput");
const basemapList = document.querySelector("#basemapList");
const chainFilterList = document.querySelector("#chainFilterList");
const cityFilterList = document.querySelector("#cityFilterList");
const clearChainButton = document.querySelector("#clearChainButton");
const clearCityButton = document.querySelector("#clearCityButton");
const locationList = document.querySelector("#locationList");
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
let currentBasemapId = "osm-muted";
let currentBaseLayer = null;
let wheelZoomTarget = null;
let wheelFrame = null;
let wheelPoint = null;
let wheelResetTimer = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

function popupHtml(feature) {
  const props = feature.properties;
  const address = props.address ? `<p class="popup-meta">${escapeHtml(props.address)}</p>` : "";
  const showtimeBlock =
    Array.isArray(props.showtimes) && props.showtimes.length
      ? `
        <div class="popup-showtimes">
          <p>${escapeHtml(props.movie_title || "")} ${escapeHtml(props.show_date || "")}</p>
          <ol>${props.showtimes
            .map((showtime) => `<li>${escapeHtml(showtime.label || showtime.time)}</li>`)
            .join("")}</ol>
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
    <p class="popup-meta">${escapeHtml(props.chain_name)} ｜ ${escapeHtml(props.city || "")}</p>
    ${address}
    ${showtimeBlock}
    <div class="popup-links">${locationLink}${officialLink}</div>
  `;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function basemapById(id) {
  return BASEMAPS.find((basemap) => basemap.id === id) || BASEMAPS[0];
}

function createTileLayer(basemap) {
  const options = {
    attribution: basemap.attribution,
    className: basemap.className || "",
    maxZoom: basemap.maxZoom || 18,
    noWrap: true,
    bounds: TAIWAN_BOUNDS,
  };
  if (basemap.subdomains) {
    options.subdomains = basemap.subdomains;
  }
  return L.tileLayer(basemap.url, options);
}

function setBasemap(id) {
  const basemap = basemapById(id);
  if (currentBaseLayer) {
    currentBaseLayer.remove();
  }
  currentBasemapId = basemap.id;
  currentBaseLayer = createTileLayer(basemap).addTo(map);
  currentBaseLayer.bringToBack();
  renderBasemapButtons();
}

function renderBasemapButtons() {
  const fragment = document.createDocumentFragment();
  for (const basemap of BASEMAPS) {
    const button = document.createElement("button");
    button.className = "basemap-option";
    button.type = "button";
    button.classList.toggle("is-selected", basemap.id === currentBasemapId);
    button.innerHTML = `
      <span>${escapeHtml(basemap.name)}</span>
      <small>${escapeHtml(basemap.note)}</small>
    `;
    button.addEventListener("click", () => setBasemap(basemap.id));
    fragment.appendChild(button);
  }
  basemapList.replaceChildren(fragment);
}

function applySmoothWheelZoom() {
  if (wheelZoomTarget === null || !wheelPoint) {
    wheelFrame = null;
    return;
  }
  const currentZoom = map.getZoom();
  const zoomDelta = wheelZoomTarget - currentZoom;
  const nextZoom =
    Math.abs(zoomDelta) < WHEEL_ZOOM_STOP_THRESHOLD
      ? wheelZoomTarget
      : currentZoom + zoomDelta * WHEEL_ZOOM_EASE;
  map.setZoomAround(wheelPoint, nextZoom, { animate: false });
  if (Math.abs(wheelZoomTarget - nextZoom) < WHEEL_ZOOM_STOP_THRESHOLD) {
    wheelFrame = null;
    return;
  }
  wheelFrame = requestAnimationFrame(applySmoothWheelZoom);
}

function handleSmoothWheel(event) {
  event.preventDefault();
  const modeMultiplier = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 100 : 1;
  const delta = event.deltaY * modeMultiplier;
  const baseZoom = wheelZoomTarget ?? map.getZoom();
  wheelZoomTarget = clamp(
    baseZoom - delta * WHEEL_ZOOM_SENSITIVITY,
    map.getMinZoom(),
    map.getMaxZoom(),
  );
  wheelPoint = map.mouseEventToContainerPoint(event);
  if (!wheelFrame) {
    wheelFrame = requestAnimationFrame(applySmoothWheelZoom);
  }
  clearTimeout(wheelResetTimer);
  wheelResetTimer = setTimeout(() => {
    wheelZoomTarget = null;
  }, WHEEL_TARGET_RESET_MS);
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
  });
  clearChainButton.classList.toggle("is-active", !selectedChain);
  clearCityButton.classList.toggle("is-active", !selectedCity);
}

function normalizeMovieData(data) {
  movieSummaries = [];
  movieFeaturesByTitle = new Map();

  if (Array.isArray(data.movies) && data.movies.length && data.movie_features) {
    for (const movie of data.movies) {
      const title = movie.title;
      if (!title) continue;
      const movieFeatures = Array.isArray(data.movie_features[title]) ? data.movie_features[title] : [];
      movieSummaries.push({
        title,
        showDate: movie.show_date || data.show_date || "",
        featureCount: movie.feature_count ?? movieFeatures.length,
      });
      movieFeaturesByTitle.set(title, movieFeatures);
    }
  } else {
    const title = data.movie_title || data.name || "目前資料";
    const fallbackFeatures = Array.isArray(data.features) ? data.features : [];
    movieSummaries.push({
      title,
      showDate: data.show_date || "",
      featureCount: data.feature_count ?? fallbackFeatures.length,
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
  const keyword = searchInput.value.trim().toLowerCase();
  const haystack = [
    props.chain_name,
    props.location_name,
    props.map_name,
    props.address,
    props.city,
  ]
    .join(" ")
    .toLowerCase();

  return (
    (!keyword || haystack.includes(keyword)) &&
    (!selectedChain || props.chain_name === selectedChain) &&
    (!selectedCity || props.city === selectedCity)
  );
}

function setActive(id) {
  activeId = id;
  document.querySelectorAll(".location-row").forEach((row) => {
    row.classList.toggle("is-active", Number(row.dataset.id) === id);
  });
}

function focusFeature(feature) {
  const props = feature.properties;
  const marker = markerById.get(props.location_id);
  if (!marker) return;
  setActive(props.location_id);
  map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), 14), { duration: 0.45 });
  marker.openPopup();
}

function renderList(filtered) {
  const fragment = document.createDocumentFragment();
  for (const feature of filtered) {
    const props = feature.properties;
    const button = document.createElement("button");
    button.className = "location-row";
    button.type = "button";
    button.dataset.id = props.location_id;
    const showtimeMeta =
      Array.isArray(props.showtimes) && props.showtimes.length
        ? `${props.showtime_count} 場 ｜ ${props.start_times}`
        : `${props.chain_name} ｜ ${props.city || "未分縣市"}`;
    button.innerHTML = `
      <span class="location-name">${escapeHtml(props.location_name)}</span>
      <span class="location-meta">${escapeHtml(showtimeMeta)}</span>
    `;
    button.addEventListener("click", () => focusFeature(feature));
    fragment.appendChild(button);
  }
  locationList.replaceChildren(fragment);
  setActive(activeId);
}

function renderMarkers(filtered) {
  markerLayer.clearLayers();
  markerById = new Map();
  for (const feature of filtered) {
    const props = feature.properties;
    const [lng, lat] = feature.geometry.coordinates;
    const marker = L.marker([lat, lng], { icon: createIcon(feature) });
    marker.bindPopup(popupHtml(feature), { minWidth: 230, maxWidth: 320 });
    marker.on("click", () => setActive(props.location_id));
    marker.addTo(markerLayer);
    markerById.set(props.location_id, marker);
  }
}

function applyFilters() {
  const filtered = features.filter(matchesFilters);
  renderMarkers(filtered);
  renderList(filtered);
  visibleCount.textContent = filtered.length;
  totalCount.textContent = features.length;
  const moviePrefix = selectedMovieTitle ? `${selectedMovieTitle}：` : "";
  summaryText.textContent = `${moviePrefix}${filtered.length} / ${features.length} 個點位`;
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
searchInput.addEventListener("input", applyFilters);
clearChainButton.addEventListener("click", () => {
  selectedChain = "";
  renderFilters();
  applyFilters();
});
clearCityButton.addEventListener("click", () => {
  selectedCity = "";
  renderFilters();
  applyFilters();
});
resetViewButton.addEventListener("click", resetView);
map.getContainer().addEventListener("wheel", handleSmoothWheel, { passive: false });

setBasemap(currentBasemapId);

loadData().catch((error) => {
  summaryText.textContent = error.message;
  console.error(error);
});
