(() => {
  const EMPTY_MOVIE_MESSAGE = "今日無上映電影";
  const EMPTY_STATE_CODE = "no_movies_today";

  function isEmptyMoviePayload(data) {
    return Boolean(data && data.empty_state === EMPTY_STATE_CODE);
  }

  function applyEmptyMovieUi(doc = document) {
    const movieSelect = doc.querySelector("#movieSelect");
    if (movieSelect) {
      const alreadyExact =
        movieSelect.options.length === 1 &&
        movieSelect.options[0].value === "" &&
        movieSelect.options[0].textContent === EMPTY_MOVIE_MESSAGE;
      if (!alreadyExact) {
        const option = doc.createElement("option");
        option.value = "";
        option.textContent = EMPTY_MOVIE_MESSAGE;
        option.selected = true;
        movieSelect.replaceChildren(option);
      }
      movieSelect.disabled = true;
      movieSelect.classList.add("is-empty");
      movieSelect.setAttribute("aria-label", EMPTY_MOVIE_MESSAGE);
    }

    const mobileMovieList = doc.querySelector("#mMovieList");
    if (mobileMovieList) {
      const first = mobileMovieList.firstElementChild;
      const alreadyExact =
        mobileMovieList.children.length === 1 &&
        first?.classList.contains("m-movie-empty") &&
        first.textContent === EMPTY_MOVIE_MESSAGE;
      if (!alreadyExact) {
        const empty = doc.createElement("div");
        empty.className = "m-movie-empty";
        empty.textContent = EMPTY_MOVIE_MESSAGE;
        mobileMovieList.replaceChildren(empty);
      }
    }
  }

  async function install() {
    try {
      const response = await fetch("data/locations.geojson", { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();
      if (!isEmptyMoviePayload(data)) return;

      const movieSelect = document.querySelector("#movieSelect");
      const mobileMovieList = document.querySelector("#mMovieList");
      const observer = new MutationObserver(() => applyEmptyMovieUi(document));
      if (movieSelect) observer.observe(movieSelect, { childList: true });
      if (mobileMovieList) observer.observe(mobileMovieList, { childList: true });
      applyEmptyMovieUi(document);
    } catch (error) {
      console.warn("Empty movie state check failed", error);
    }
  }

  window.MuseEmptyState = {
    EMPTY_MOVIE_MESSAGE,
    EMPTY_STATE_CODE,
    isEmptyMoviePayload,
    applyEmptyMovieUi,
    install,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", install, { once: true });
  } else {
    install();
  }
})();
