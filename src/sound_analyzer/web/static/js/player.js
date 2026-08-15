import { api } from "./api.js";
import { formatClock, formatDuration, titleCase } from "./format.js";
import { draw, lazyWave, loadPeaks, setProgress } from "./waveform.js";

const audio = new Audio();
audio.preload = "auto";

const dom = {};
const listeners = new Set();

let queue = [];
let index = -1;
let current = null;
let currentPeaks = null;

function emit() {
  for (const listener of listeners) listener(current, audio.paused);
}

export function onChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function currentClip() {
  return current;
}

export function isPlaying(clipId) {
  return Boolean(current && current.id === clipId && !audio.paused);
}

function renderPlayIcon() {
  const playing = !audio.paused && current;
  dom.toggle.querySelector('[data-icon="play"]').style.display = playing ? "none" : "";
  dom.toggle.querySelector('[data-icon="pause"]').style.display = playing ? "" : "none";
  dom.toggle.setAttribute("aria-label", playing ? "Pausar" : "Reproducir");
  dom.toggle.title = playing ? "Pausar (espacio)" : "Reproducir (espacio)";
}

function renderMeta() {
  dom.root.classList.toggle("is-empty", !current);
  if (!current) {
    dom.title.textContent = "Nada sonando";
    dom.sub.textContent = "Elige un sonido de la lista";
    return;
  }
  dom.title.textContent = current.name;
  const bits = [current.category ? titleCase(current.category) : null, current.filename].filter(Boolean);
  dom.sub.textContent = bits.join(" · ");
  dom.sub.title = current.relpath;
  dom.total.textContent = formatDuration(current.duration);
}

function renderProgress() {
  const duration = audio.duration || current?.duration || 0;
  const ratio = duration ? Math.min(1, audio.currentTime / duration) : 0;
  dom.elapsed.textContent = formatClock(audio.currentTime);
  if (currentPeaks) draw(dom.wave, currentPeaks, { progress: ratio, barWidth: 2, gap: 1 });
  if (dom.art.__canvas) setProgress(dom.art.__canvas, ratio);
}

async function loadWave(clip) {
  currentPeaks = null;
  draw(dom.wave, null, { progress: 0 });
  const peaks = await loadPeaks(clip.id, 480);
  if (current && current.id === clip.id) {
    currentPeaks = peaks;
    renderProgress();
  }
}

export function play(clip, list = null) {
  if (list) {
    queue = list;
    index = list.findIndex((item) => item.id === clip.id);
  } else if (!queue.length) {
    queue = [clip];
    index = 0;
  }
  current = clip;
  audio.src = api.audioUrl(clip.id);
  audio.play().catch(() => {
    /* autoplay policies or a missing file; the UI already shows the state */
  });
  renderMeta();
  dom.art.innerHTML = "";
  const art = document.createElement("canvas");
  dom.art.append(art);
  lazyWave(art, clip.id, { buckets: 64, barWidth: 2, gap: 1 });
  dom.art.__canvas = art;
  loadWave(clip);
  emit();
}

export function toggle() {
  if (!current) {
    if (queue.length) play(queue[0]);
    return;
  }
  if (audio.paused) audio.play().catch(() => {});
  else audio.pause();
}

export function playAt(offset) {
  if (!queue.length) return;
  const next = index + offset;
  if (next < 0 || next >= queue.length) return;
  index = next;
  play(queue[index], queue);
}

export function setQueue(list) {
  queue = list;
  if (current) index = list.findIndex((item) => item.id === current.id);
}

function seekFromEvent(event) {
  const rect = dom.wave.getBoundingClientRect();
  const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
  const duration = audio.duration || current?.duration || 0;
  if (duration) audio.currentTime = ratio * duration;
}

export function mount(refs) {
  Object.assign(dom, refs);

  dom.toggle.addEventListener("click", toggle);
  dom.prev.addEventListener("click", () => playAt(-1));
  dom.next.addEventListener("click", () => playAt(1));

  dom.wave.tabIndex = 0;
  dom.wave.setAttribute("role", "slider");
  dom.wave.setAttribute("aria-label", "Posición de reproducción");
  dom.wave.addEventListener("click", seekFromEvent);
  dom.wave.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight") audio.currentTime += 1;
    if (event.key === "ArrowLeft") audio.currentTime -= 1;
  });

  dom.loop.addEventListener("click", () => {
    audio.loop = !audio.loop;
    dom.loop.classList.toggle("is-on", audio.loop);
    dom.loop.setAttribute("aria-pressed", String(audio.loop));
  });

  dom.volume.addEventListener("input", () => {
    audio.volume = Number(dom.volume.value);
    dom.volume.style.setProperty("--fill", `${audio.volume * 100}%`);
  });
  dom.volume.style.setProperty("--fill", "100%");

  dom.download.addEventListener("click", () => {
    if (current) window.location.href = api.downloadUrl(current.id);
  });

  dom.reveal.addEventListener("click", () => {
    if (current) api.reveal(current.id).catch(() => {});
  });

  audio.addEventListener("timeupdate", renderProgress);
  audio.addEventListener("loadedmetadata", renderProgress);
  audio.addEventListener("play", () => {
    renderPlayIcon();
    emit();
  });
  audio.addEventListener("pause", () => {
    renderPlayIcon();
    emit();
  });
  audio.addEventListener("ended", () => {
    if (!audio.loop) playAt(1);
  });

  window.addEventListener("resize", () => {
    if (currentPeaks) renderProgress();
  });

  renderPlayIcon();
  renderMeta();
}
