import { api } from "./api.js";
import {
  circleCard,
  clipCard,
  clipRow,
  listHead,
  notice,
  rail,
  selectRow,
  skeletonCards,
  skeletonRows,
  toast,
} from "./components.js";
import { el } from "./dom.js";
import { formatCount, plural, titleCase } from "./format.js";
import * as player from "./player.js";

const main = document.getElementById("main");
const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const searchClear = document.getElementById("search-clear");
const refInput = document.getElementById("ref-input");
const topSelect = document.getElementById("top-select");

const PAGE_SIZE = 60;
const SORTS = [
  ["name", "Nombre"],
  ["short", "Cortos"],
  ["long", "Largos"],
  ["recent", "Recientes"],
  ["confidence", "Confianza"],
];

const state = {
  library: null,
  items: [],
  selected: -1,
  top: 25,
  reference: null,
  token: 0,
};

/* ------------------------------------------------------------------ boot */

player.mount({
  root: document.getElementById("player"),
  art: document.getElementById("player-art"),
  title: document.getElementById("player-title"),
  sub: document.getElementById("player-sub"),
  toggle: document.getElementById("player-toggle"),
  prev: document.getElementById("player-prev"),
  next: document.getElementById("player-next"),
  wave: document.getElementById("player-wave"),
  elapsed: document.getElementById("player-elapsed"),
  total: document.getElementById("player-total"),
  loop: document.getElementById("player-loop"),
  volume: document.getElementById("player-volume"),
  download: document.getElementById("player-download"),
  reveal: document.getElementById("player-reveal"),
});

async function boot() {
  try {
    state.library = await api.library();
  } catch (error) {
    main.replaceChildren(
      notice("No se pudo leer el banco", [
        "El servidor respondió: ",
        el("code", {}, String(error.message)),
      ]),
    );
    return;
  }
  window.__libraryPath = state.library.path;
  renderSidebar();
  window.addEventListener("hashchange", render);
  render();
}

/* --------------------------------------------------------------- sidebar */

function renderSidebar() {
  const { path, stats, categories, folders } = state.library;
  document.getElementById("library-path").textContent = path;
  document.getElementById("library-path").title = path;
  document.getElementById("library-stats").replaceChildren(
    el("span", {}, plural(stats.clips, "sonido", "sonidos")),
    el("span", {}, plural(stats.files, "archivo", "archivos")),
    el("span", {}, `${formatCount(stats.tagged)} etiquetados`),
  );
  document.getElementById("nav-all-count").textContent = formatCount(stats.clips);

  document.getElementById("category-nav").replaceChildren(
    ...categories.map((category) => {
      const group = el(
        "li",
        { class: "nav-group" },
        el(
          "a",
          { class: "nav-item", href: `#/category/${encodeURIComponent(category.name)}`, dataset: { nav: `category:${category.name}` } },
          el("span", { class: "nav-item__glyph", "aria-hidden": "true" }, category.name[0].toUpperCase()),
          titleCase(category.name),
          el("span", { class: "nav-item__count" }, formatCount(category.count)),
        ),
        el(
          "ul",
          { class: "nav-sub" },
          ...category.subcategories.map((sub) =>
            el(
              "li",
              {},
              el(
                "a",
                {
                  class: "nav-item",
                  href: `#/category/${encodeURIComponent(category.name)}/${encodeURIComponent(sub.name)}`,
                  dataset: { nav: `category:${category.name}/${sub.name}` },
                },
                sub.name,
                el("span", { class: "nav-item__count" }, formatCount(sub.count)),
              ),
            ),
          ),
        ),
      );
      return group;
    }),
  );

  // A flat bank has a single implicit folder; listing it would say nothing.
  const hasFolders = folders.filter((folder) => folder.path).length > 0;
  document.getElementById("folder-section").hidden = !hasFolders;
  document.getElementById("folder-nav").replaceChildren(
    ...folders
      .filter((folder) => folder.path)
      .map((folder) =>
        el(
          "li",
          {},
          el(
            "a",
            { class: "nav-item", href: `#/folder/${encodeURIComponent(folder.path)}`, dataset: { nav: `folder:${folder.path}` } },
            el("span", { class: "nav-item__glyph", "aria-hidden": "true" }, "/"),
            folder.name,
            el("span", { class: "nav-item__count" }, formatCount(folder.count)),
          ),
        ),
      ),
  );
}

function markActiveNav(key) {
  document.querySelectorAll("[data-nav]").forEach((node) => {
    const active = node.dataset.nav === key;
    node.classList.toggle("is-active", active);
    if (active) node.closest(".nav-group")?.classList.add("is-open");
  });
  document.querySelectorAll(".nav-group").forEach((group) => {
    if (!group.querySelector(".is-active")) group.classList.remove("is-open");
  });
}

/* ---------------------------------------------------------------- router */

function parseHash() {
  const raw = location.hash.slice(1) || "/browse";
  const [path, query] = raw.split("?");
  return {
    parts: path.split("/").filter(Boolean).map(decodeURIComponent),
    params: new URLSearchParams(query || ""),
  };
}

function render() {
  state.token += 1;
  state.items = [];
  state.selected = -1;
  main.scrollTop = 0;
  const token = state.token;
  const { parts, params } = parseHash();
  const [route, ...rest] = parts;

  if (route === "search") {
    const query = params.get("q") || "";
    searchInput.value = query;
    syncSearchField();
    markActiveNav(null);
    renderSearch(query, token);
    return;
  }

  if (route === "reference") {
    markActiveNav(null);
    renderReference(token);
    return;
  }

  searchInput.value = "";
  syncSearchField();

  if (route === "category") {
    const [category, subcategory] = rest;
    markActiveNav(`category:${[category, subcategory].filter(Boolean).join("/")}`);
    renderList(
      {
        title: titleCase(subcategory || category),
        kind: subcategory ? `${category} · subcategoría` : "Categoría",
        filters: { category, subcategory },
      },
      params,
      token,
    );
    return;
  }

  if (route === "folder") {
    const folder = rest.join("/");
    markActiveNav(`folder:${folder}`);
    renderList({ title: folder || "Raíz", kind: "Carpeta", filters: { folder } }, params, token);
    return;
  }

  if (route === "all") {
    markActiveNav("all");
    renderList({ title: "Todos los sonidos", kind: "Banco completo", filters: {} }, params, token);
    return;
  }

  markActiveNav("browse");
  renderBrowse(token);
}

/* ----------------------------------------------------------- browse view */

function renderBrowse(token) {
  const { stats, categories, folders } = state.library;

  if (!stats.clips) {
    main.replaceChildren(emptyIndexNotice());
    return;
  }

  const view = el(
    "div",
    { class: "view" },
    el(
      "div",
      { class: "view-head" },
      el(
        "div",
        {},
        el("h1", { class: "view-title" }, "Explorar"),
        el(
          "div",
          { class: "view-sub" },
          `${plural(stats.clips, "sonido", "sonidos")} · ${plural(stats.files, "archivo", "archivos")} · ${plural(categories.length, "categoría", "categorías")}`,
        ),
      ),
      el(
        "div",
        { class: "view-head__actions" },
        el(
          "div",
          { class: "shortcuts" },
          el("span", {}, el("kbd", {}, "/"), " buscar"),
          el("span", {}, el("kbd", {}, "espacio"), " play"),
          el("span", {}, el("kbd", {}, "↑"), el("kbd", {}, "↓"), " navegar"),
        ),
      ),
    ),
  );

  const recent = rail("Añadidos recientemente", "#/all?sort=recent", skeletonCards());
  const shorts = rail("Golpes y sonidos cortos", "#/all?sort=short", skeletonCards());
  view.append(recent);

  view.append(
    rail(
      "Categorías",
      null,
      categories.map((category) =>
        circleCard(
          titleCase(category.name),
          plural(category.count, "sonido", "sonidos"),
          `#/category/${encodeURIComponent(category.name)}`,
        ),
      ),
    ),
  );

  view.append(shorts);

  const topCategories = state.library.categories.slice(0, 4);
  const categoryRails = topCategories.map((category) => {
    const section = rail(
      titleCase(category.name),
      `#/category/${encodeURIComponent(category.name)}`,
      skeletonCards(6),
    );
    view.append(section);
    return { section, params: { category: category.name, sort: "confidence", limit: 12 } };
  });

  const namedFolders = folders.filter((folder) => folder.path);
  if (namedFolders.length > 1) {
    view.append(
      rail(
        "Carpetas",
        null,
        namedFolders.map((folder) =>
          circleCard(folder.name, plural(folder.count, "sonido", "sonidos"), `#/folder/${encodeURIComponent(folder.path)}`),
        ),
      ),
    );
  }

  main.replaceChildren(view);

  fillRail(recent, { sort: "recent", limit: 12 }, token);
  fillRail(shorts, { sort: "short", limit: 12 }, token);
  for (const entry of categoryRails) fillRail(entry.section, entry.params, token);
}

async function fillRail(section, params, token) {
  const track = section.querySelector(".rail__track");
  try {
    const data = await api.browse(params);
    if (token !== state.token) return;
    if (!data.results.length) {
      section.remove();
      return;
    }
    track.replaceChildren(...data.results.map((clip) => clipCard(clip, data.results)));
  } catch (error) {
    if (token !== state.token) return;
    track.replaceChildren(el("div", { class: "loading-line" }, String(error.message)));
  }
}

/* ------------------------------------------------------------- list view */

function renderList(config, params, token) {
  const sort = params.get("sort") || "name";
  const filters = { ...config.filters, sort };

  const container = el("div", { class: "list" });
  const status = el("div", { class: "view-sub" }, "Cargando…");
  const sortControl = el(
    "div",
    { class: "segmented", role: "group", "aria-label": "Ordenar" },
    ...SORTS.map(([value, label]) =>
      el(
        "button",
        {
          type: "button",
          class: value === sort ? "is-active" : "",
          onclick: () => {
            const next = new URLSearchParams(params);
            next.set("sort", value);
            location.hash = `${location.hash.split("?")[0]}?${next.toString()}`;
          },
        },
        label,
      ),
    ),
  );

  const view = el(
    "div",
    { class: "view" },
    el(
      "div",
      { class: "view-head" },
      el("div", {}, el("h1", { class: "view-title" }, config.title), status),
      el("div", { class: "view-head__actions" }, sortControl),
    ),
    el("div", {}, listHead(), container),
  );
  main.replaceChildren(view);
  container.append(...skeletonRows(8));

  let offset = 0;
  let total = 0;
  let loading = false;
  let done = false;

  const sentinel = el("div", { style: "height:1px" });

  async function loadMore() {
    if (loading || done) return;
    loading = true;
    try {
      const data = await api.browse({ ...filters, limit: PAGE_SIZE, offset });
      if (token !== state.token) return;
      if (!offset) container.replaceChildren();
      total = data.total;
      offset += data.results.length;
      done = offset >= total || !data.results.length;
      const start = state.items.length;
      state.items.push(...data.results);
      container.append(...data.results.map((clip, i) => clipRow(clip, start + i, state.items)));
      player.setQueue(state.items);
      status.textContent = `${plural(total, "sonido", "sonidos")}${config.kind ? ` · ${config.kind}` : ""}`;
      if (!total) container.replaceChildren(notice("Sin resultados", "No hay sonidos con estos filtros."));
      if (done) sentinel.remove();
      else container.after(sentinel);
    } catch (error) {
      if (token !== state.token) return;
      container.replaceChildren(notice("Error al cargar", String(error.message)));
      done = true;
    } finally {
      loading = false;
    }
  }

  const observer = new IntersectionObserver(
    (entries) => {
      if (token !== state.token) {
        observer.disconnect();
        return;
      }
      if (entries.some((entry) => entry.isIntersecting)) loadMore();
    },
    { root: main, rootMargin: "600px" },
  );
  observer.observe(sentinel);
  loadMore();
}

/* ----------------------------------------------------------- search view */

function searchShell(title, subtitle) {
  const body = el("div", {});
  const view = el(
    "div",
    { class: "view" },
    el("div", { class: "view-head" }, el("div", {}, el("h1", { class: "view-title" }, title), el("div", { class: "view-sub" }, subtitle))),
    body,
  );
  main.replaceChildren(view);
  return body;
}

function loadingBlock(message) {
  return el(
    "div",
    {},
    el("div", { class: "loading-line" }, el("span", { class: "spinner" }), message),
    el("div", { style: "height:12px" }),
    ...skeletonRows(6),
  );
}

async function renderSearch(query, token) {
  if (!query.trim()) {
    location.hash = "#/browse";
    return;
  }
  if (!state.library.stats.embedded) {
    main.replaceChildren(emptyIndexNotice());
    return;
  }
  const body = searchShell(`«${query}»`, "Búsqueda semántica en todo el banco");
  body.replaceChildren(loadingBlock("Buscando… la primera consulta carga el modelo CLAP y puede tardar un poco."));
  try {
    const data = await api.search({ q: query, top: state.top });
    if (token !== state.token) return;
    showResults(body, data.results, `Sin coincidencias para «${query}».`);
  } catch (error) {
    if (token !== state.token) return;
    body.replaceChildren(notice("La búsqueda falló", String(error.message)));
  }
}

async function renderReference(token) {
  const file = state.reference;
  if (!file) {
    location.hash = "#/browse";
    return;
  }
  const body = searchShell(file.name, "Sonidos parecidos a tu audio de referencia");
  body.replaceChildren(loadingBlock("Analizando el audio de referencia…"));
  try {
    const data = await api.searchAudio(file, { top: state.top });
    if (token !== state.token) return;
    showResults(body, data.results, "Sin sonidos parecidos.");
  } catch (error) {
    if (token !== state.token) return;
    body.replaceChildren(notice("La búsqueda falló", String(error.message)));
  }
}

function showResults(body, results, emptyMessage) {
  if (!results.length) {
    body.replaceChildren(notice("Sin resultados", emptyMessage));
    return;
  }
  state.items = results;
  player.setQueue(results);
  const container = el("div", { class: "list" }, ...results.map((clip, i) => clipRow(clip, i, results)));
  body.replaceChildren(listHead(), container);
}

function emptyIndexNotice() {
  return notice(
    "Este banco todavía no está indexado",
    [
      "Ejecuta ",
      el("code", {}, `sound-analyzer index "${state.library.path}"`),
      " para escanear, segmentar y etiquetar los sonidos. Luego recarga esta página.",
    ],
    [el("button", { class: "pill pill--white pill--compact", type: "button", onclick: () => location.reload() }, "Recargar")],
  );
}

/* --------------------------------------------------------------- search UI */

function syncSearchField() {
  searchForm.classList.toggle("has-value", Boolean(searchInput.value));
}

function submitSearch() {
  const query = searchInput.value.trim();
  if (!query) return;
  const next = `#/search?q=${encodeURIComponent(query)}`;
  if (location.hash === next) render();
  else location.hash = next;
}

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitSearch();
});
searchInput.addEventListener("input", syncSearchField);
searchClear.addEventListener("click", () => {
  searchInput.value = "";
  syncSearchField();
  searchInput.focus();
  if (parseHash().parts[0] === "search") location.hash = "#/browse";
});
document.getElementById("search-submit").addEventListener("click", submitSearch);
document.getElementById("nav-back").addEventListener("click", () => history.back());

topSelect.addEventListener("click", (event) => {
  const button = event.target.closest("[data-top]");
  if (!button) return;
  state.top = Number(button.dataset.top);
  topSelect.querySelectorAll("button").forEach((node) => node.classList.toggle("is-active", node === button));
  const route = parseHash().parts[0];
  if (route === "search" || route === "reference") render();
});

refInput.addEventListener("change", () => {
  const file = refInput.files?.[0];
  if (!file) return;
  state.reference = file;
  toast(`Referencia: ${file.name}`);
  if (location.hash === "#/reference") render();
  else location.hash = "#/reference";
  refInput.value = "";
});

/* ------------------------------------------------------------- shortcuts */

main.addEventListener("click", (event) => {
  const row = event.target.closest(".row");
  if (row) state.selected = Number(row.dataset.position);
});

function isTyping(target) {
  return target instanceof HTMLElement && (target.tagName === "INPUT" || target.tagName === "TEXTAREA");
}

function moveSelection(delta) {
  if (!state.items.length) return;
  const next = Math.min(state.items.length - 1, Math.max(0, state.selected + delta));
  state.selected = state.selected === -1 ? 0 : next;
  selectRow(state.selected);
  const row = main.querySelector(`.row[data-position="${state.selected}"]`);
  row?.scrollIntoView({ block: "nearest" });
}

document.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey) return;

  if (event.key === "/" && !isTyping(event.target)) {
    event.preventDefault();
    searchInput.focus();
    searchInput.select();
    return;
  }

  if (event.key === "Escape") {
    if (isTyping(event.target)) event.target.blur();
    return;
  }

  if (isTyping(event.target)) return;

  if (event.key === " ") {
    event.preventDefault();
    player.toggle();
    return;
  }

  if (event.key === "ArrowDown" || event.key === "j") {
    event.preventDefault();
    moveSelection(1);
    return;
  }

  if (event.key === "ArrowUp" || event.key === "k") {
    event.preventDefault();
    moveSelection(-1);
    return;
  }

  if (event.key === "Enter" && state.selected >= 0) {
    event.preventDefault();
    player.play(state.items[state.selected], state.items);
  }
});

boot();
