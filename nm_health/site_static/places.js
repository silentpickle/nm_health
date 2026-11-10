// Copyright (c) 2026 nm_health contributors
// Places: search, filters, strips and paging over places.json. Without it the page lists every place as a plain link.

import {
  PEST_FLAG_TEXT,
  RED_GROUP,
  chip,
  count,
  day,
  el,
  fmt,
  fmtShort,
  loadPlaces,
  placeHref,
  recentText,
  strip,
} from "./shared.js";

/** @typedef {import("./shared.js").Place} Place */
/** @typedef {import("./shared.js").Places} Places */

const PAGE_SIZE = 60;
const ALL = "all";
/** @type {Record<string, (place: Place) => boolean>} */
const FILTERS = {
  all: () => true,
  red: (place) => place.closure !== "",
  pests: (place) => place.pests,
  employee: (place) => place.employee,
};
const state = { q: "", f: ALL, shown: PAGE_SIZE };

/**
 * @param {Place} place
 * @param {string[]} words
 */
function matches(place, words) {
  const keep = FILTERS[state.f] ?? FILTERS.all;
  if (keep !== undefined && !keep(place)) {
    return false;
  }
  const hay =
    `${place.name} ${place.legal ?? ""} ${place.address}`.toLowerCase();
  return words.every((word) => hay.includes(word));
}

/** @param {Place} place */
function flags(place) {
  const [latest] = place.history;
  const out = [];
  if (place.pests) {
    out.push(el("span", { class: "flag", text: PEST_FLAG_TEXT }));
  }
  if (place.closure && latest?.level !== "r") {
    out.push(
      el("span", {
        class: "flag",
        text: `${RED_GROUP} ${fmtShort(day(place.closure))}`,
      }),
    );
  }
  return out;
}

/** @param {Place} place */
function row(place) {
  const [latest] = place.history;
  const meta = el("div", { class: "meta" }, [
    el("span", { class: "data", text: place.address }),
  ]);
  if (latest) {
    meta.append(chip(latest), el("span", { text: fmt(latest.date) }));
  }
  meta.append(...flags(place));
  const info = el("div", { class: "info" }, [
    el("div", { class: "nm", text: place.name }),
    meta,
    el("div", { class: "recent", text: recentText(place) }),
  ]);
  return el("li", {}, [
    el("a", { class: "row", href: placeHref(place.id) }, [info, strip(place)]),
  ]);
}

/**
 * @param {Places} data
 * @param {{ caveat: HTMLElement, status: HTMLElement, rows: HTMLElement, more: HTMLButtonElement }} view
 */
function draw(data, view) {
  const words = state.q.toLowerCase().split(/\s+/).filter(Boolean);
  const hits = data.places.filter((place) => matches(place, words));
  view.caveat.hidden = state.f !== "pests";
  view.status.textContent = `${count(hits.length)} of ${count(data.places.length)} places`;
  view.rows.replaceChildren(...hits.slice(0, state.shown).map(row));
  const left = hits.length - state.shown;
  view.more.hidden = left <= 0;
  view.more.textContent = `Show ${count(Math.min(PAGE_SIZE, left))} more`;
}

/** @param {Places} data */
function buildView(data) {
  const caveat = el("p", {
    class: "note",
    text: `Only inspections with inspector notes on file can show pest citations: ${count(data.withNotes)} of ${count(data.inspections)} in this period.`,
  });
  const status = el("p", { class: "eyebrow", role: "status" });
  const rows = el("ul", { class: "rows" });
  const more = el("button", { class: "more", type: "button" });
  return { caveat, status, rows, more };
}

/**
 * @param {HTMLElement} tools
 * @param {() => void} redraw
 */
function listen(tools, redraw) {
  const input = tools.querySelector("input");
  input?.addEventListener("input", () => {
    state.q = input.value;
    state.shown = PAGE_SIZE;
    redraw();
  });
  const buttons = tools.querySelectorAll("button[data-f]");
  tools.addEventListener("click", (event) => {
    const pressed =
      event.target instanceof Element
        ? event.target.closest("button[data-f]")
        : null;
    if (!(pressed instanceof HTMLButtonElement)) {
      return;
    }
    state.f = pressed.dataset.f ?? ALL;
    state.shown = PAGE_SIZE;
    for (const button of buttons) {
      button.setAttribute("aria-pressed", String(button === pressed));
    }
    redraw();
  });
}

async function main() {
  const tools = document.getElementById("tools");
  const list = document.getElementById("list");
  const data = await loadPlaces();
  if (!tools || !list || !data) {
    return;
  }
  const view = buildView(data);
  const redraw = () => {
    draw(data, view);
  };
  view.more.addEventListener("click", () => {
    state.shown += PAGE_SIZE;
    redraw();
  });
  listen(tools, redraw);
  list.replaceChildren(view.caveat, view.status, view.rows, view.more);
  tools.hidden = false;
  redraw();
}

await main();
