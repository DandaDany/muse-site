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

function createFakeElement() {
  const classes = new Set();
  const attributes = new Map();
  const element = {
    value: "",
    textContent: "",
    selected: false,
    disabled: false,
    className: "",
    classList: {
      add(name) {
        classes.add(name);
      },
      contains(name) {
        return classes.has(name) || element.className.split(/\s+/).includes(name);
      },
    },
    setAttribute(name, value) {
      attributes.set(name, value);
    },
    getAttribute(name) {
      return attributes.get(name);
    },
  };
  return element;
}

const movieSelect = createFakeElement();
movieSelect.options = [Object.assign(createFakeElement(), { value: "old", textContent: "舊電影 (1)" })];
movieSelect.replaceChildren = (...nodes) => {
  movieSelect.options = nodes;
};

const mobileMovieList = createFakeElement();
mobileMovieList._children = [Object.assign(createFakeElement(), { textContent: "舊電影" })];
Object.defineProperty(mobileMovieList, "children", { get: () => mobileMovieList._children });
Object.defineProperty(mobileMovieList, "firstElementChild", {
  get: () => mobileMovieList._children[0] || null,
});
mobileMovieList.replaceChildren = (...nodes) => {
  mobileMovieList._children = nodes;
};

const fakeDocument = {
  querySelector(selector) {
    if (selector === "#movieSelect") return movieSelect;
    if (selector === "#mMovieList") return mobileMovieList;
    return null;
  },
  createElement() {
    return createFakeElement();
  },
};

api.applyEmptyMovieUi(fakeDocument);
assert.strictEqual(movieSelect.options.length, 1);
assert.strictEqual(movieSelect.options[0].value, "");
assert.strictEqual(movieSelect.options[0].textContent, "今日無上映電影");
assert.strictEqual(movieSelect.disabled, true);
assert.strictEqual(movieSelect.classList.contains("is-empty"), true);
assert.strictEqual(movieSelect.getAttribute("aria-label"), "今日無上映電影");
assert.strictEqual(mobileMovieList.children.length, 1);
assert.strictEqual(mobileMovieList.firstElementChild.className, "m-movie-empty");
assert.strictEqual(mobileMovieList.firstElementChild.textContent, "今日無上映電影");

console.log("frontend_empty_state_test: ok");
