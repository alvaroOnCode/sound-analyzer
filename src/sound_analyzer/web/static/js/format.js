const decimal = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat("es-ES");

export function formatClock(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const total = Math.floor(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** Short durations read better in seconds; SFX libraries are full of them. */
export function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${decimal.format(seconds)} s`;
  return formatClock(seconds);
}

export function formatCount(value) {
  return integer.format(value ?? 0);
}

export function plural(value, singular, many) {
  return `${integer.format(value ?? 0)} ${value === 1 ? singular : many}`;
}

export function formatChannels(channels) {
  if (channels === 1) return "mono";
  if (channels === 2) return "estéreo";
  if (Number.isFinite(channels) && channels > 0) return `${channels} canales`;
  return null;
}

export function formatSampleRate(rate) {
  if (!Number.isFinite(rate) || rate <= 0) return null;
  return `${decimal.format(rate / 1000)} kHz`;
}

export function titleCase(text) {
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}
