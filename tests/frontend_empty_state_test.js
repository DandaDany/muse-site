const assert = require("assert");
const path = require("path");

const listeners = new Map();
global.window = {};
global.document = {
  readyState: "loading",
  addEventListener(name, handler) {
    listeners.set(name, handler);
  },
};

require(path.join(__dirname, "..", "web", "empty-state.js"));

const api = global.window.MuseEmptyState;
assert(api, "MuseEmptyState should be exposed");
assert.strictEqual(api.EMPTY_MOVIE_MESSAGE, "今日無上映電影");
assert.strictEqual(api.EMPTY_STATE_CODE, "no_movies_today");
assert.strictEqual(api.isEmptyMoviePayload({ empty_state: "no_movies_today" }), true);
assert.strictEqual(api.isEmptyMoviePayload({ movies: [] }), false);
assert.strictEqual(api.isEmptyMoviePayload(null), false);
assert.strictEqual(typeof listeners.get("DOMContentLoaded"), "function");

console.log("frontend_empty_state_test: ok");
