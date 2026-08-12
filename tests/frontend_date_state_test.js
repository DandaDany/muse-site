const assert = require("assert");
const { dateChipLabel, taipeiToday } = require("../web/date-state.js");

assert.strictEqual(dateChipLabel("2026-08-12", "2026-08-12"), "今天 8/12");
assert.strictEqual(dateChipLabel("2026-08-13", "2026-08-12"), "明天 8/13");
assert.strictEqual(dateChipLabel("2026-08-14", "2026-08-12"), "五 8/14");
assert.strictEqual(taipeiToday(new Date("2026-08-11T16:30:00Z")), "2026-08-12");

console.log("frontend date state regression tests passed");
