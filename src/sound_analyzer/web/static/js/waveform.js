import { api } from "./api.js";

/* The waveform is this app's album art: it is the only thing on screen that
   carries the content's own shape, so everything else stays monochrome. */

const REST = "rgba(255, 255, 255, 0.38)";
const PLAYED = "#1ed760";
const MAX_PARALLEL = 4;

const cache = new Map();
const pending = [];
let running = 0;

function drain() {
  while (running < MAX_PARALLEL && pending.length) {
    const job = pending.shift();
    running += 1;
    api
      .peaks(job.id, job.buckets)
      .then((data) => {
        cache.set(job.key, data.peaks);
        job.resolve(data.peaks);
      })
      .catch(() => job.resolve(null))
      .finally(() => {
        running -= 1;
        drain();
      });
  }
}

export function loadPeaks(id, buckets) {
  const key = `${id}:${buckets}`;
  if (cache.has(key)) return Promise.resolve(cache.get(key));
  return new Promise((resolve) => {
    pending.push({ id, buckets, key, resolve });
    drain();
  });
}

function resample(peaks, count) {
  if (!peaks || !peaks.length) return new Array(count).fill(0);
  if (peaks.length === count) return peaks;
  const out = new Array(count);
  const ratio = peaks.length / count;
  for (let i = 0; i < count; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.max(start + 1, Math.floor((i + 1) * ratio));
    let peak = 0;
    for (let j = start; j < end && j < peaks.length; j += 1) {
      if (peaks[j] > peak) peak = peaks[j];
    }
    out[i] = peak;
  }
  return out;
}

export function draw(canvas, peaks, { progress = 0, played = PLAYED, rest = REST, barWidth = 2, gap = 1 } = {}) {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return;
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const step = barWidth + gap;
  const count = Math.max(1, Math.floor(width / step));
  const values = resample(peaks, count);
  const middle = height / 2;
  const limit = progress * width;

  for (let i = 0; i < count; i += 1) {
    const x = i * step;
    // Linear amplitude turns anything with a sharp attack into a dotted line,
    // so the tail stays readable through a perceptual curve.
    const amplitude = Math.max(0.04, values[i] ** 0.6);
    const barHeight = Math.max(2, amplitude * (height - 2));
    ctx.fillStyle = x + barWidth <= limit ? played : rest;
    ctx.beginPath();
    ctx.roundRect(x, middle - barHeight / 2, barWidth, barHeight, barWidth / 2);
    ctx.fill();
  }
}

const observer = new IntersectionObserver(
  (entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const canvas = entry.target;
      observer.unobserve(canvas);
      const state = canvas.__wave;
      if (!state) continue;
      loadPeaks(state.id, state.buckets).then((peaks) => {
        if (!peaks) return;
        state.peaks = peaks;
        draw(canvas, peaks, state.options);
      });
    }
  },
  { rootMargin: "200px" },
);

/** Draw a clip's waveform once the canvas scrolls into view. */
export function lazyWave(canvas, id, { buckets = 96, ...options } = {}) {
  canvas.__wave = { id, buckets, peaks: null, options };
  draw(canvas, null, options);
  observer.observe(canvas);
  return canvas;
}

export function setProgress(canvas, progress) {
  const state = canvas.__wave;
  if (!state) return;
  state.options = { ...state.options, progress };
  if (state.peaks) draw(canvas, state.peaks, state.options);
}
