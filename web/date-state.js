(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MuseDateState = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const TAIPEI_TIME_ZONE = "Asia/Taipei";
  const weekday = ["日", "一", "二", "三", "四", "五", "六"];

  function taipeiToday(now = new Date()) {
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat("en-CA", {
        timeZone: TAIPEI_TIME_ZONE,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      })
        .formatToParts(now)
        .filter((part) => ["year", "month", "day"].includes(part.type))
        .map((part) => [part.type, part.value]),
    );
    return `${parts.year}-${parts.month}-${parts.day}`;
  }

  function parseIsoDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
    return match ? new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]))) : null;
  }

  function dateChipLabel(value, today = taipeiToday()) {
    const target = parseIsoDate(value);
    const base = parseIsoDate(today);
    if (!target || !base) return String(value || "");
    const offset = Math.round((target - base) / 86400000);
    const prefix = offset === 0 ? "今天" : offset === 1 ? "明天" : weekday[target.getUTCDay()];
    return `${prefix} ${target.getUTCMonth() + 1}/${target.getUTCDate()}`;
  }

  function formatUpdatedAt(value) {
    if (!value) return "";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "";
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat("en-CA", {
        timeZone: TAIPEI_TIME_ZONE,
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      })
        .formatToParts(parsed)
        .filter((part) => ["month", "day", "hour", "minute"].includes(part.type))
        .map((part) => [part.type, part.value]),
    );
    return `${Number(parts.month)}/${Number(parts.day)} ${parts.hour}:${parts.minute}`;
  }

  function summaryTextForDate(showDate, updatedAt, today = taipeiToday()) {
    const target = parseIsoDate(showDate);
    const base = parseIsoDate(today);
    const isFuture = Boolean(target && base && target > base);
    const formatted = formatUpdatedAt(updatedAt);
    if (isFuture) {
      return formatted ? `未來場次將持續更新 · 更新於 ${formatted}` : "未來場次將持續更新";
    }
    return formatted ? `更新於 ${formatted}` : "";
  }

  function availableDatesForMovie(byDate) {
    if (!byDate) return [];
    const entries = byDate instanceof Map ? [...byDate.entries()] : Object.entries(byDate);
    return entries
      .filter(([showDate, features]) => showDate && Array.isArray(features) && features.length > 0)
      .map(([showDate]) => showDate)
      .sort();
  }

  function selectedDateForMovie(currentDate, movieDates, today = taipeiToday()) {
    const dates = [...new Set(Array.isArray(movieDates) ? movieDates.filter(Boolean) : [])].sort();
    if (dates.includes(currentDate)) return currentDate;
    if (dates.includes(today)) return today;
    return dates[0] || today;
  }

  return {
    TAIPEI_TIME_ZONE,
    availableDatesForMovie,
    dateChipLabel,
    formatUpdatedAt,
    selectedDateForMovie,
    summaryTextForDate,
    taipeiToday,
  };
});
