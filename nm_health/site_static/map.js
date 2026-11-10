// Copyright (c) 2026 nm_health contributors
// Map: one dot per place from places.json, drawn by packages/citymap (copied into the site as citymap.js).

import { renderMap } from "citymap";
import { count, fmt, loadPlaces, placeHref } from "./shared.js";

/** @typedef {import("citymap").Basemap} Basemap */
/** @typedef {import("citymap").MapPoint} MapPoint */
/** @typedef {import("./shared.js").Place} Place */

const POINT_RADIUS = 3.5;
const PEST_KIND = "-pest";
const state = { redOnly: false };

/** @returns {Promise<Basemap | null>} */
async function loadBasemap() {
  const response = await fetch("albuquerque.geojson");
  if (!response.ok) {
    return null;
  }
  /** @type {unknown} */
  const raw = await response.json();
  return /** @type {Basemap} */ (raw);
}

/**
 * @param {Place} place
 * @returns {MapPoint | null}
 */
function point(place) {
  const [latest] = place.history;
  if (!place.latLng || !latest) {
    return null;
  }
  const [lat, lng] = place.latLng;
  const pests = place.pests ? "; roaches or rodents cited" : "";
  return {
    lat,
    lng,
    kind: latest.level + (place.pests ? PEST_KIND : ""),
    href: placeHref(place.id),
    label: `${place.name}: ${latest.status}, ${fmt(latest.date)}${pests}`,
  };
}

/**
 * @param {HTMLElement} box
 * @param {Basemap} basemap
 * @param {Place[]} places
 */
function draw(box, basemap, places) {
  const shown = places.filter(
    (place) => !state.redOnly || place.closure !== "",
  );
  const points = shown.map(point).filter((p) => p !== null);
  renderMap(box, basemap, points, {
    zoom: true,
    label: `Albuquerque, ${count(points.length)} places`,
    pointRadius: POINT_RADIUS,
  });
  // Keyboard and screen-reader users browse by name on the Places page; 1,400 focusable dots would be a trap.
  for (const link of box.querySelectorAll(".cm-point-link")) {
    link.setAttribute("tabindex", "-1");
    link.setAttribute("aria-hidden", "true");
  }
}

async function main() {
  const box = document.getElementById("map");
  const toggle = document.getElementById("red-only");
  const [basemap, data] = await Promise.all([loadBasemap(), loadPlaces()]);
  if (!box || !toggle || !basemap || !data) {
    return;
  }
  toggle.addEventListener("click", () => {
    state.redOnly = !state.redOnly;
    toggle.setAttribute("aria-pressed", String(state.redOnly));
    draw(box, basemap, data.places);
  });
  toggle.hidden = false;
  draw(box, basemap, data.places);
}

await main();
