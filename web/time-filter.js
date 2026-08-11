(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MuseTimeFilter = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const TAIPEI_TIME_ZONE = "Asia/Taipei";
  const MANUAL_SNAP_MINUTES = 15;

  const taipeiClock = new Intl.DateTimeFormat("en-GB", {
    timeZone: TAIPEI_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function taipeiNowMinutes(now = new Date()) {
    const parts = Object.fromEntries(
      taipeiClock
        .formatToParts(now)
        .filter((part) => part.type === "hour" || part.type === "minute")
        .map((part) => [part.type, Number(part.value)]),
    );
    return clamp((parts.hour || 0) * 60 + (parts.minute || 0), 0, 1439);
  }

  function formatMinutes(minutes) {
    const safeMinutes = clamp(Math.round(minutes), 0, 1439);
    const hour = Math.floor(safeMinutes / 60);
    const minute = safeMinutes % 60;
    return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  }

  function snapManualMinutes(minutes) {
    return clamp(Math.round(minutes / MANUAL_SNAP_MINUTES) * MANUAL_SNAP_MINUTES, 0, 1425);
  }

  function manualTimeReached(nowMinutes, manualEarliest) {
    return nowMinutes >= manualEarliest;
  }

  function showtimePassesTimeState(showtimeMinute, state, periodRanges) {
    if (!Number.isFinite(showtimeMinute) || showtimeMinute < 0 || showtimeMinute >= 1440) return false;
    if (showtimeMinute <= state.nowMinutes) return false;
    if (state.mode === "manual" && showtimeMinute < state.manualEarliest) return false;

    if (state.period !== "all") {
      const [periodStart, periodEnd] = periodRanges[state.period] || [0, 1440];
      if (showtimeMinute < periodStart || showtimeMinute >= periodEnd) return false;
    }
    return true;
  }

  return {
    MANUAL_SNAP_MINUTES,
    TAIPEI_TIME_ZONE,
    formatMinutes,
    manualTimeReached,
    showtimePassesTimeState,
    snapManualMinutes,
    taipeiNowMinutes,
  };
});
