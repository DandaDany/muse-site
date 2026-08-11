const assert = require("node:assert/strict");
const {
  formatMinutes,
  manualTimeReached,
  showtimePassesTimeState,
  snapManualMinutes,
  taipeiNowMinutes,
} = require("../web/time-filter.js");

const PERIOD_RANGES = {
  all: [0, 1440],
  morning: [0, 720],
  afternoon: [720, 1080],
  evening: [1080, 1440],
};
const showtimes = [17 * 60 + 30, 17 * 60 + 37, 17 * 60 + 40, 18 * 60, 19 * 60 + 15, 20 * 60 + 30];

function visible(nowMinutes, mode = "auto", manualEarliest = nowMinutes, period = "all") {
  return showtimes.filter((showtimeMinute) =>
    showtimePassesTimeState(
      showtimeMinute,
      { nowMinutes, mode, manualEarliest, period },
      PERIOD_RANGES,
    ),
  );
}

assert.equal(taipeiNowMinutes(new Date("2026-08-11T09:37:00Z")), 17 * 60 + 37);
assert.equal(formatMinutes(17 * 60 + 37), "17:37");

// A: AUTO excludes a showtime equal to now, but keeps every later showtime.
assert.deepEqual(visible(17 * 60 + 37), [17 * 60 + 40, 18 * 60, 19 * 60 + 15, 20 * 60 + 30]);

// B: advancing now to 17:40 removes the 17:40 showtime as already started.
assert.deepEqual(visible(17 * 60 + 40), [18 * 60, 19 * 60 + 15, 20 * 60 + 30]);

// C/D: MANUAL is inclusive and remains fixed while now is earlier.
assert.deepEqual(visible(17 * 60 + 37, "manual", 19 * 60 + 15), [19 * 60 + 15, 20 * 60 + 30]);
assert.deepEqual(visible(18 * 60 + 30, "manual", 19 * 60 + 15), [19 * 60 + 15, 20 * 60 + 30]);

// E: when now reaches MANUAL, the equal showtime is expired and the mode should return to AUTO.
assert.equal(manualTimeReached(19 * 60 + 15, 19 * 60 + 15), true);
assert.deepEqual(visible(19 * 60 + 15, "manual", 19 * 60 + 15), [20 * 60 + 30]);

assert.equal(snapManualMinutes(19 * 60 + 8), 19 * 60 + 15);
assert.equal(snapManualMinutes(19 * 60 + 21), 19 * 60 + 15);

// Quick periods remain an intersection with now.
assert.deepEqual(visible(17 * 60 + 37, "auto", 0, "afternoon"), [17 * 60 + 40]);
assert.deepEqual(visible(17 * 60 + 37, "auto", 0, "evening"), [18 * 60, 19 * 60 + 15, 20 * 60 + 30]);

console.log("frontend time filter regression tests passed");
