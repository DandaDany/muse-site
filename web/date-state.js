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

  return { TAIPEI_TIME_ZONE, dateChipLabel, taipeiToday };
});
