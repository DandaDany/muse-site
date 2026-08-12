const assert = require("assert");
const {
  availableDatesForMovie,
  dateChipLabel,
  formatUpdatedAt,
  selectedDateForMovie,
  summaryTextForDate,
  taipeiToday,
} = require("../web/date-state.js");

assert.strictEqual(dateChipLabel("2026-08-12", "2026-08-12"), "今天 8/12");
assert.strictEqual(dateChipLabel("2026-08-13", "2026-08-12"), "明天 8/13");
assert.strictEqual(dateChipLabel("2026-08-14", "2026-08-12"), "五 8/14");
assert.strictEqual(taipeiToday(new Date("2026-08-11T16:30:00Z")), "2026-08-12");
assert.strictEqual(formatUpdatedAt("2026-08-12T07:05:23+08:00"), "8/12 07:05");
assert.strictEqual(
  summaryTextForDate("2026-08-12", "2026-08-12T07:05:23+08:00", "2026-08-12"),
  "更新於 8/12 07:05",
);
assert.strictEqual(
  summaryTextForDate("2026-08-13", "2026-08-12T07:05:23+08:00", "2026-08-12"),
  "未來場次將持續更新 · 更新於 8/12 07:05",
);
assert.strictEqual(
  summaryTextForDate("2026-08-12", "2026-08-12T07:05:23+08:00", "2026-08-12"),
  "更新於 8/12 07:05",
);
assert.strictEqual(summaryTextForDate("2026-08-12", null, "2026-08-12"), "");
assert.strictEqual(
  summaryTextForDate("2026-08-13", null, "2026-08-12"),
  "未來場次將持續更新",
);
assert.strictEqual(formatUpdatedAt("not-a-date"), "");

const movieA = new Map([
  ["2026-08-12", [{}]],
  ["2026-08-13", [{}]],
  ["2026-08-14", [{}]],
]);
const movieB = new Map([
  ["2026-08-12", [{}]],
  ["2026-08-15", [{}]],
]);
assert.deepStrictEqual(availableDatesForMovie(movieB), ["2026-08-12", "2026-08-15"]);
assert.strictEqual(
  selectedDateForMovie("2026-08-14", availableDatesForMovie(movieB), "2026-08-12"),
  "2026-08-12",
);
assert.strictEqual(
  selectedDateForMovie("2026-08-12", availableDatesForMovie(movieB), "2026-08-12"),
  "2026-08-12",
);
assert.strictEqual(
  selectedDateForMovie("2026-08-15", availableDatesForMovie(movieA), "2026-08-12"),
  "2026-08-12",
);
assert.strictEqual(
  selectedDateForMovie("2026-08-15", availableDatesForMovie(movieB), "2026-08-12"),
  "2026-08-15",
);

console.log("frontend date state regression tests passed");
