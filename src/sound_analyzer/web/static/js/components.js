import { api } from "./api.js";
import { PATHS, el, icon } from "./dom.js";
import { formatChannels, formatDuration, formatSampleRate, titleCase } from "./format.js";
import * as player from "./player.js";
import { lazyWave } from "./waveform.js";

const rows = new Map();
const cards = new Map();

export function toast(message) {
  const node = document.getElementById("toast");
  node.textContent = message;
  node.classList.add("is-visible");
  clearTimeout(node.__timer);
  node.__timer = setTimeout(() => node.classList.remove("is-visible"), 2200);
}

function copyPath(clip) {
  const full = `${window.__libraryPath || ""}/${clip.relpath}`;
  navigator.clipboard
    .writeText(full)
    .then(() => toast("Ruta copiada"))
    .catch(() => toast("No se pudo copiar la ruta"));
}

function tagChips(clip, limit = 3) {
  const chips = (clip.tags || []).slice(0, limit).map((tag) =>
    el(
      "button",
      {
        class: "chip",
        type: "button",
        title: `${tag.label}${tag.score ? ` · ${Math.round(tag.score * 100)}%` : ""}`,
        onclick: (event) => {
          event.stopPropagation();
          location.hash = `#/search?q=${encodeURIComponent(tag.label)}`;
        },
      },
      tag.label,
    ),
  );
  if (!chips.length && clip.category) {
    chips.push(el("span", { class: "chip" }, clip.category));
  }
  return chips;
}

function scoreMeter(score) {
  if (typeof score !== "number") return null;
  const percent = Math.max(0, Math.min(100, Math.round(score * 100)));
  return el(
    "span",
    { class: "score", title: `Similitud ${percent}%` },
    el("span", { class: "score__bar" }, el("i", { style: `width:${percent}%` })),
    `${percent}%`,
  );
}

function actionButton(title, path, handler) {
  return el(
    "button",
    {
      class: "row__action",
      type: "button",
      title,
      "aria-label": title,
      onclick: (event) => {
        event.stopPropagation();
        handler();
      },
    },
    icon(path, 14),
  );
}

export function clipRow(clip, position, list) {
  const playButton = el(
    "button",
    {
      class: "play-btn play-btn--ghost play-btn--sm",
      type: "button",
      title: "Reproducir",
      "aria-label": `Reproducir ${clip.name}`,
      onclick: (event) => {
        event.stopPropagation();
        togglePlay(clip, list);
      },
    },
    icon(PATHS.play, 14),
  );

  const wave = el("canvas", { class: "row__wave" });
  const meta = [
    scoreMeter(clip.score),
    clip.subcategory || clip.category
      ? el("span", {}, [clip.category, clip.subcategory].filter(Boolean).join(" · "))
      : null,
    el("span", { class: "truncate", title: clip.relpath }, clip.filename),
    el("span", { class: "row__tech" }, techLine(clip)),
  ].filter(Boolean);

  const row = el(
    "div",
    {
      class: "row",
      role: "button",
      tabIndex: 0,
      dataset: { id: String(clip.id), position: String(position) },
      ondblclick: () => togglePlay(clip, list),
      onclick: (event) => {
        if (event.detail === 0) return;
        selectRow(position);
      },
      onkeydown: (event) => {
        if (event.key === "Enter") togglePlay(clip, list);
      },
    },
    el("div", { class: "row__index" }, el("span", { class: "row__index-number" }, String(position + 1)), playButton),
    el(
      "div",
      { class: "row__main" },
      el("div", { class: "row__title truncate", title: clip.name }, clip.name),
      el("div", { class: "row__sub truncate" }, ...interleave(meta, " · ")),
    ),
    el("div", { class: "row__tags" }, ...tagChips(clip)),
    wave,
    el("div", { class: "row__duration" }, formatDuration(clip.duration)),
    el(
      "div",
      { class: "row__actions" },
      actionButton("Descargar", PATHS.download, () => {
        window.location.href = api.downloadUrl(clip.id);
      }),
      actionButton("Copiar ruta", PATHS.copy, () => copyPath(clip)),
      actionButton("Mostrar en el explorador", PATHS.folder, () =>
        api.reveal(clip.id).catch(() => toast("No se pudo abrir el explorador")),
      ),
    ),
  );

  lazyWave(wave, clip.id, { buckets: 96, barWidth: 2, gap: 1 });
  rows.set(clip.id, row);
  syncRow(row, clip.id);
  return row;
}

function interleave(nodes, separator) {
  const out = [];
  nodes.forEach((node, index) => {
    if (index) out.push(separator);
    out.push(node);
  });
  return out;
}

export function clipCard(clip, list) {
  const wave = el("canvas");
  const card = el(
    "div",
    {
      class: "card",
      role: "button",
      tabIndex: 0,
      dataset: { id: String(clip.id) },
      title: clip.relpath,
      onclick: () => togglePlay(clip, list),
      onkeydown: (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          togglePlay(clip, list);
        }
      },
    },
    el(
      "div",
      { class: "card__art" },
      wave,
      el(
        "button",
        {
          class: "play-btn card__play",
          type: "button",
          tabIndex: -1,
          "aria-hidden": "true",
        },
        icon(PATHS.play, 14),
      ),
    ),
    el("div", { class: "card__title truncate" }, clip.name),
    el(
      "div",
      { class: "card__meta truncate" },
      formatDuration(clip.duration),
      clip.category ? " · " : null,
      clip.category ? titleCase(clip.category) : null,
    ),
  );
  lazyWave(wave, clip.id, { buckets: 96, barWidth: 3, gap: 2 });
  cards.set(clip.id, card);
  syncCard(card, clip.id);
  return card;
}

export function circleCard(label, sublabel, href) {
  return el(
    "a",
    { class: "circle-card", href },
    el("div", { class: "circle-card__art", "aria-hidden": "true" }, (label[0] || "?").toUpperCase()),
    el("div", { class: "circle-card__title truncate" }, label),
    el("div", { class: "circle-card__sub" }, sublabel),
  );
}

export function rail(title, href, children) {
  const track = el("div", { class: "rail__track" }, ...children);
  const scrollBy = (direction) => track.scrollBy({ left: direction * track.clientWidth * 0.8, behavior: "smooth" });
  const viewport = el(
    "div",
    { class: "rail__viewport" },
    el(
      "button",
      { class: "rail__nav rail__nav--prev", type: "button", "aria-label": "Anterior", onclick: () => scrollBy(-1) },
      icon(PATHS.chevronLeft, 14),
    ),
    track,
    el(
      "button",
      { class: "rail__nav rail__nav--next", type: "button", "aria-label": "Siguiente", onclick: () => scrollBy(1) },
      icon(PATHS.chevronRight, 14),
    ),
  );
  return el(
    "section",
    { class: "rail" },
    el(
      "div",
      { class: "rail__head" },
      el("h2", { class: "rail__title" }, title),
      href ? el("a", { class: "rail__more", href }, "Ver todo") : null,
    ),
    viewport,
  );
}

export function listHead() {
  return el(
    "div",
    { class: "list__head" },
    el("span", {}, "#"),
    el("span", {}, "Sonido"),
    el("span", { class: "list__head-tags" }, "Tags"),
    el("span", { class: "list__head-wave" }, "Forma de onda"),
    el("span", { style: "text-align:right" }, "Duración"),
    el("span", {}, ""),
  );
}

export function notice(title, body, actions = []) {
  return el(
    "div",
    { class: "notice" },
    el("h3", { class: "notice__title" }, title),
    el("p", { class: "notice__body" }, ...(Array.isArray(body) ? body : [body])),
    actions.length ? el("div", { class: "view-head__actions" }, ...actions) : null,
  );
}

export function skeletonCards(count = 8) {
  return Array.from({ length: count }, () => el("div", { class: "skeleton skeleton-card" }));
}

export function skeletonRows(count = 8) {
  return Array.from({ length: count }, () => el("div", { class: "skeleton skeleton-row" }));
}

export function techLine(clip) {
  return [formatSampleRate(clip.sample_rate), formatChannels(clip.channels), clip.codec].filter(Boolean).join(" · ");
}

function togglePlay(clip, list) {
  if (player.currentClip()?.id === clip.id) player.toggle();
  else player.play(clip, list || null);
}

export function selectRow(position) {
  const nodes = document.querySelectorAll(".row");
  nodes.forEach((node) => node.classList.toggle("is-selected", Number(node.dataset.position) === position));
}

function syncRow(row, clipId) {
  const playing = player.isPlaying(clipId);
  row.classList.toggle("is-playing", playing);
  const button = row.querySelector(".play-btn");
  if (button) {
    button.replaceChildren(icon(playing ? PATHS.pause : PATHS.play, 14));
  }
}

function syncCard(card, clipId) {
  const playing = player.isPlaying(clipId);
  card.classList.toggle("is-playing", playing);
  const button = card.querySelector(".card__play");
  if (button) button.replaceChildren(icon(playing ? PATHS.pause : PATHS.play, 14));
}

player.onChange(() => {
  for (const [id, row] of rows) {
    if (!row.isConnected) rows.delete(id);
    else syncRow(row, id);
  }
  for (const [id, card] of cards) {
    if (!card.isConnected) cards.delete(id);
    else syncCard(card, id);
  }
});
