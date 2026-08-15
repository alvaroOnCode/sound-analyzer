/** Minimal hyperscript so views stay declarative without a build step. */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "style") node.setAttribute("style", value);
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key in node) node[key] = value;
    else node.setAttribute(key, value);
  }
  append(node, children);
  return node;
}

function append(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function icon(path, size = 16) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("fill", "currentColor");
  svg.setAttribute("aria-hidden", "true");
  const shape = document.createElementNS("http://www.w3.org/2000/svg", "path");
  shape.setAttribute("d", path);
  svg.append(shape);
  return svg;
}

export const PATHS = {
  play: "M4 2.6v10.8L13 8z",
  pause: "M3.5 2h3.2v12H3.5zM9.3 2h3.2v12H9.3z",
  download: "M7.25 1v7.19L4.53 5.47 3.47 6.53 8 11.06l4.53-4.53-1.06-1.06-2.72 2.72V1zM2.5 12.5h11V14h-11z",
  folder: "M1.5 2.5h4.1l1.2 1.5h7.7v9.5h-13zm1.5 1.5v6.5h10V5.5H6.1L4.9 4z",
  copy: "M5 1h8v10h-1.5V2.5H5zM3 4h7.5v11H3zm1.5 1.5v8h4.5v-8z",
  chevronLeft: "M10.3 2.3 4.6 8l5.7 5.7 1.1-1.1L6.8 8l4.6-4.6z",
  chevronRight: "M5.7 2.3 11.4 8l-5.7 5.7-1.1-1.1L9.2 8 4.6 3.4z",
};
