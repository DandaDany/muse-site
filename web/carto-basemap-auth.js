(() => {
  const key = String(window.MuseRuntimeConfig?.cartoBasemapKey || "").trim();
  if (!key || !window.L?.TileLayer) return;

  const proto = L.TileLayer.prototype;
  const originalGetTileUrl = proto.getTileUrl;
  if (originalGetTileUrl.__museCartoKeyWrapped) return;

  function getTileUrlWithCartoKey(coords) {
    const url = originalGetTileUrl.call(this, coords);
    if (!/basemaps\.cartocdn\.com\//i.test(url) || /[?&]key=/.test(url)) {
      return url;
    }
    const separator = url.includes("?") ? "&" : "?";
    return `${url}${separator}key=${encodeURIComponent(key)}`;
  }

  getTileUrlWithCartoKey.__museCartoKeyWrapped = true;
  proto.getTileUrl = getTileUrlWithCartoKey;
})();
