// Copyright (c) 2026 nm_health contributors
// Shared by places.js and map.js: reading places.json, dates, status chips and week strips.
// The pages work without any of this: every place is listed and linked in the HTML.

/** @typedef {[number, number]} VisitRow  [days before places.json's "today", index into statuses] */
/**
 * One place in places.json (see nm_health/site.py places_json).
 * @typedef {[string, string, string | null, string, string, VisitRow[], number, number, string, [number, number] | null, string]} PlaceRow
 */
/** @typedef {{ today: string, statuses: [string, string][], inspections: number, withNotes: number, places: PlaceRow[] }} PlacesFile */
/** @typedef {{ date: Date, status: string, level: string }} Visit */
/**
 * @typedef {object} Place
 * @property {string} id
 * @property {string} name
 * @property {string | null} legal
 * @property {string} address
 * @property {string} strip
 * @property {Visit[]} history newest first, up to 8
 * @property {number} more inspections beyond history
 * @property {boolean} pests roaches or rodents cited in notes on file
 * @property {boolean} employee employee items cited
 * @property {string} closure latest closure or unsatisfactory start, or ""
 * @property {[number, number] | null} latLng
 * @property {boolean} closureInForce some permit's result in force is a closure
 * @property {string} reopened status flag, e.g. "1 of 2 permits closed" or "Closed 6 days, reopened Oct 9", else ""
 */
/** @typedef {{ inspections: number, withNotes: number, places: Place[] }} Places */

export const RED_GROUP = "Closure or unsatisfactory";
export const PEST_FLAG_TEXT = "Roaches or rodents cited";
const FLAG_PESTS = 1;
const FLAG_EMPLOYEE = 2;
const FLAG_CLOSURE_IN_FORCE = 4;
const RECENT_MAX = 3;
const NOON = "T12:00:00";
const LOCALE = "en-US";
const NO_STATUS = /** @type {[string, string]} */ (["", "n"]);
/** Strip cell code -> classes (same table as nm_health/viewmodel.py CELL_CLASSES). */
/** @type {Record<string, string>} */
const CELL_CLASSES = {
  ".": "",
  g: "g",
  y: "y",
  r: "r",
  n: "n2",
  G: "g so",
  Y: "y so",
  R: "r so",
  N: "n2 so",
  1: "g p",
  2: "y p",
  3: "r p",
  0: "n2 p",
};

/**
 * @template {keyof HTMLElementTagNameMap} K
 * @param {K} tag
 * @param {Record<string, string>} [attrs] attributes; "text" sets the text content
 * @param {(Node | string)[]} [kids]
 * @returns {HTMLElementTagNameMap[K]}
 */
export function el(tag, attrs = {}, kids = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") {
      node.textContent = value;
    } else {
      node.setAttribute(key, value);
    }
  }
  node.append(...kids);
  return node;
}

/**
 * Local noon on an ISO date (noon keeps daylight-saving shifts from changing the day).
 * @param {string} iso
 */
export const day = (iso) => new Date(iso + NOON);

/**
 * "Oct 29, 2026".
 * @param {Date} date
 */
export function fmt(date) {
  return date.toLocaleDateString(LOCALE, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * "Oct 29".
 * @param {Date} date
 */
export function fmtShort(date) {
  return date.toLocaleDateString(LOCALE, {
    month: "short",
    day: "numeric",
  });
}

/**
 * "1,426".
 * @param {number} n
 */
export function count(n) {
  return n.toLocaleString(LOCALE);
}

/**
 * The city's own status words in placard colour.
 * @param {Visit} visit
 */
export function chip(visit) {
  return el("span", { class: "chip " + visit.level, text: visit.status });
}

/**
 * @param {Place} place
 * @returns {string}
 */
function stripLabel(place) {
  const listed = place.history
    .map((v) => `${fmt(v.date)}: ${v.status}`)
    .join("; ");
  const extra = place.more > 0 ? `; and ${count(place.more)} more` : "";
  return `Inspections in the last ${String(place.strip.length)} weeks: ${listed}${extra}`;
}

/**
 * The week strip (one cell per week in place.strip), newest week on the right.
 * @param {Place} place
 */
export function strip(place) {
  const box = el("div", {
    class: "strip",
    role: "img",
    "aria-label": stripLabel(place),
  });
  for (const code of place.strip) {
    const classes = CELL_CLASSES[code] ?? "";
    box.append(classes ? el("i", { class: classes }) : el("i"));
  }
  return box;
}

/**
 * The newest dated statuses on one line (shown on phones instead of the strip).
 * @param {Place} place
 */
export function recentText(place) {
  return place.history
    .slice(0, RECENT_MAX)
    .map((v) => `${fmtShort(v.date)} ${v.status}`)
    .join(" · ");
}

/** @param {string} slug */
export const placeHref = (slug) => `place/${encodeURIComponent(slug)}.html`;

/**
 * @param {PlacesFile} file
 * @param {PlaceRow} row
 * @returns {Place}
 */
function decode(file, row) {
  const [
    id,
    name,
    legal,
    address,
    stripCode,
    visits,
    more,
    flags,
    closure,
    latLng,
    reopened,
  ] = row;
  const history = visits.map(([daysAgo, index]) => {
    const date = day(file.today);
    date.setDate(date.getDate() - daysAgo);
    const [status, level] = file.statuses[index] ?? NO_STATUS;
    return { date, status, level };
  });
  return {
    id,
    name,
    legal,
    address,
    strip: stripCode,
    history,
    more,
    pests: (flags & FLAG_PESTS) !== 0,
    employee: (flags & FLAG_EMPLOYEE) !== 0,
    closureInForce: (flags & FLAG_CLOSURE_IN_FORCE) !== 0,
    closure,
    latLng,
    reopened,
  };
}

/**
 * places.json, decoded; null when it can't be fetched (the page keeps its plain HTML list).
 * @returns {Promise<Places | null>}
 */
export async function loadPlaces() {
  const response = await fetch("places.json");
  if (!response.ok) {
    return null;
  }
  /** @type {unknown} */
  const raw = await response.json();
  const file = /** @type {PlacesFile} */ (raw);
  const places = file.places.map((row) => decode(file, row));
  return { inspections: file.inspections, withNotes: file.withNotes, places };
}
