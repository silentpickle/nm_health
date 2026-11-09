// Copyright (c) 2026 nm_health contributors
// citymap: draw a basemap GeoJSON (from `citymap build`) and a list of points as inline SVG. Zero dependencies,
// no tiles, no network. Styling is CSS classes plus custom properties (see citymap.css).

/** @typedef {[number, number]} Position  [lon, lat], the GeoJSON order */
/** @typedef {[number, number, number, number]} BBox  [west, south, east, north], the GeoJSON order */
/**
 * @typedef {{ type: "LineString", coordinates: Position[] }
 *   | { type: "MultiLineString", coordinates: Position[][] }
 *   | { type: "Polygon", coordinates: Position[][] }
 *   | { type: "MultiPolygon", coordinates: Position[][][] }} Geometry
 */
/** @typedef {{ type: "Feature", properties: { kind: string, name?: string }, geometry: Geometry }} Feature */
/** @typedef {{ type: "FeatureCollection", bbox: BBox, attribution?: string, features: Feature[] }} Basemap */
/** @typedef {{ lat: number, lng: number, kind?: string, label?: string, href?: string }} MapPoint */
/**
 * @typedef {object} MapOptions
 * @property {boolean} [zoom] Show +/- buttons; zoom with Ctrl/Cmd+wheel, trackpad or touch pinch; drag to pan
 *   (default false).
 * @property {string} [label] Accessible name of the map (default "Map").
 * @property {number} [width] Width of the SVG coordinate space; the height follows the bbox (default 1000).
 * @property {number} [pointRadius] Point radius in CSS pixels, kept at any map size and zoom (default 5).
 * @property {number} [maxZoom] Deepest zoom factor (default 8).
 */
/** @typedef {{ width: number, height: number, project: (lng: number, lat: number) => Position }} Fit */
/** @typedef {{ x: number, y: number, width: number, height: number }} ViewBox */
/** @typedef {{ x: number, y: number, distance: number }} Gesture */
/** @typedef {{ setUnitsPerPx: (value: number) => void, setZoom: (value: number) => void }} Scaler */

const SVG_NS = "http://www.w3.org/2000/svg";
export const ATTRIBUTION = "© OpenStreetMap contributors (ODbL)";
const COPYRIGHT_URL = "https://www.openstreetmap.org/copyright";
const DEFAULT_WIDTH = 1000;
const DEFAULT_POINT_RADIUS = 5;
const DEFAULT_MAX_ZOOM = 8;
const PATH_SCALE = 10; // path numbers keep one decimal
const ATTRIBUTION_INSET = 6;
const ATTRIBUTION_PX = 11;
const BUTTON_ZOOM_STEP = 1.5;
const WHEEL_ZOOM_STEP = 1.2;
const DEGREES_PER_HALF_TURN = 180;
const DEGREES_TO_RADIANS = Math.PI / DEGREES_PER_HALF_TURN;
const HALF = 0.5;
const PINCH_POINTERS = 2;

/** Basemap layers, drawn bottom to top; points go on top of all of them. */
const LAYERS = ["water", "river", "roads", "boundary"];
/** @type {Record<string, string>} */
const LAYER_OF_KIND = {
  water: "water",
  river: "river",
  road_medium: "roads",
  road_major: "roads",
  boundary: "boundary",
};
/** @type {Record<string, number>} */
const DRAW_ORDER = { road_medium: 0, road_major: 1 };

// --- Pure helpers (exported for tests) ---

/**
 * Equirectangular projection fitted to a bbox: x grows east, y grows south, longitude scaled by cos(mid-latitude)
 * so a kilometre is the same length both ways.
 * @param {BBox} bbox
 * @param {number} [width]
 * @returns {Fit}
 */
export function fitBBox(bbox, width = DEFAULT_WIDTH) {
  const [west, south, east, north] = bbox;
  if (!(east > west && north > south && width > 0)) {
    throw new RangeError(
      `citymap: bbox must be [west, south, east, north] with area; got ${bbox.join(",")}`,
    );
  }
  const kx = Math.cos((south + north) * HALF * DEGREES_TO_RADIANS);
  const scale = width / ((east - west) * kx);
  return {
    width,
    height: (north - south) * scale,
    project: (lng, lat) => [(lng - west) * kx * scale, (north - lat) * scale],
  };
}

/**
 * @param {number} n
 * @returns {string}
 */
function fmt(n) {
  return String(Math.round(n * PATH_SCALE) / PATH_SCALE);
}

/**
 * @param {Position[]} line
 * @param {Fit["project"]} project
 * @param {boolean} close
 * @returns {string}
 */
function linePath(line, project, close) {
  const parts = line.map(([lng, lat], i) => {
    const [x, y] = project(lng, lat);
    return `${i === 0 ? "M" : "L"}${fmt(x)} ${fmt(y)}`;
  });
  return parts.join("") + (close && parts.length > 0 ? "Z" : "");
}

/**
 * SVG path data for a GeoJSON line or polygon geometry (polygon rings are closed with Z).
 * @param {Geometry} geometry
 * @param {Fit["project"]} project
 * @returns {string}
 */
export function geometryPath(geometry, project) {
  switch (geometry.type) {
    case "LineString":
      return linePath(geometry.coordinates, project, false);
    case "MultiLineString":
      return geometry.coordinates
        .map((line) => linePath(line, project, false))
        .join("");
    case "Polygon":
      return geometry.coordinates
        .map((ring) => linePath(ring, project, true))
        .join("");
    case "MultiPolygon":
      return geometry.coordinates
        .flat()
        .map((ring) => linePath(ring, project, true))
        .join("");
  }
}

/**
 * Keep a view box inside the full map: no wider than it, and not panned past its edges.
 * @param {ViewBox} view
 * @param {ViewBox} full
 * @returns {ViewBox}
 */
export function clampViewBox(view, full) {
  const width = Math.min(view.width, full.width);
  const height = Math.min(view.height, full.height);
  const x = Math.min(Math.max(view.x, full.x), full.x + full.width - width);
  const y = Math.min(Math.max(view.y, full.y), full.y + full.height - height);
  return { x, y, width, height };
}

/**
 * Zoom a view box by factor (above 1 zooms in) keeping the focus point (in view box units) where it is on screen.
 * @param {ViewBox} view
 * @param {number} factor
 * @param {{ x: number, y: number }} focus
 * @param {ViewBox} full
 * @param {number} [maxZoom]
 * @returns {ViewBox}
 */
export function zoomViewBox(
  view,
  factor,
  focus,
  full,
  maxZoom = DEFAULT_MAX_ZOOM,
) {
  const minWidth = full.width / maxZoom;
  const width = Math.min(full.width, Math.max(minWidth, view.width / factor));
  const ratio = width / view.width;
  const zoomed = {
    x: focus.x - (focus.x - view.x) * ratio,
    y: focus.y - (focus.y - view.y) * ratio,
    width,
    height: view.height * ratio,
  };
  return clampViewBox(zoomed, full);
}

/**
 * Centre of the active pointers and, for two, the distance between them.
 * @param {{ x: number, y: number }[]} pointers
 * @returns {Gesture}
 */
export function gestureOf(pointers) {
  const n = pointers.length || 1;
  const x = pointers.reduce((sum, p) => sum + p.x, 0) / n;
  const y = pointers.reduce((sum, p) => sum + p.y, 0) / n;
  const [a, b] = pointers;
  const distance = a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0;
  return { x, y, distance };
}

/**
 * A CSS class suffix from any kind string: unknown kinds still get a stable, valid class.
 * @param {string} kind
 * @returns {string}
 */
export function kindClass(kind) {
  return kind.replace(/[^A-Za-z0-9_-]/g, "-") || "default";
}

// --- DOM building ---

/**
 * @param {string} name
 * @param {Record<string, string | number>} [attrs]
 * @returns {SVGElement}
 */
function svgEl(name, attrs = {}) {
  const el = /** @type {SVGElement} */ (document.createElementNS(SVG_NS, name));
  for (const [key, value] of Object.entries(attrs)) {
    el.setAttribute(key, String(value));
  }
  return el;
}

/**
 * @param {string} text
 * @returns {SVGElement}
 */
function titleEl(text) {
  const title = svgEl("title");
  title.textContent = text;
  return title;
}

/**
 * @param {Feature[]} features
 * @returns {Map<string, Feature[]>}
 */
function featuresByLayer(features) {
  /** @type {Map<string, Feature[]>} */
  const layers = new Map(LAYERS.map((name) => [name, []]));
  for (const feature of features) {
    const layer = LAYER_OF_KIND[feature.properties.kind];
    layers.get(layer ?? "")?.push(feature);
  }
  const roads = layers.get("roads") ?? [];
  roads.sort(
    (a, b) =>
      (DRAW_ORDER[a.properties.kind] ?? 0) -
      (DRAW_ORDER[b.properties.kind] ?? 0),
  );
  return layers;
}

/**
 * @param {Feature} feature
 * @param {Fit} fit
 * @returns {SVGElement}
 */
function featurePath(feature, fit) {
  const { kind, name } = feature.properties;
  const path = svgEl("path", {
    class: `cm-feature cm-${kindClass(kind)}`,
    d: geometryPath(feature.geometry, fit.project),
  });
  if (name) {
    path.dataset.name = name;
  }
  return path;
}

/**
 * The basemap as one labelled image group: water, river, roads, boundary.
 * @param {Basemap} basemap
 * @param {Fit} fit
 * @param {string} label
 * @returns {SVGElement}
 */
function basemapGroup(basemap, fit, label) {
  const group = svgEl("g", {
    class: "cm-basemap",
    role: "img",
    "aria-label": `${label}: basemap`,
  });
  group.append(titleEl(`${label}: basemap of roads, rivers and boundary`));
  for (const [name, features] of featuresByLayer(basemap.features)) {
    const layer = svgEl("g", { class: `cm-layer cm-layer-${name}` });
    layer.append(...features.map((feature) => featurePath(feature, fit)));
    group.append(layer);
  }
  return group;
}

/**
 * One point: a circle with an accessible name, wrapped in a link when it has an href.
 * @param {MapPoint} point
 * @param {Fit} fit
 * @returns {SVGElement}
 */
function pointEl(point, fit) {
  const kind = point.kind ?? "default";
  const name = point.label ?? kind;
  const [cx, cy] = fit.project(point.lng, point.lat);
  const circle = svgEl("circle", {
    class: `pt pt-${kindClass(kind)}`,
    cx: fmt(cx),
    cy: fmt(cy),
  });
  circle.append(titleEl(name));
  if (!point.href) {
    circle.setAttribute("role", "img");
    circle.setAttribute("aria-label", name);
    return circle;
  }
  const link = svgEl("a", {
    href: point.href,
    class: "cm-point-link",
    "aria-label": name,
  });
  link.append(circle);
  return link;
}

/**
 * @param {MapPoint[]} points
 * @param {Fit} fit
 * @returns {SVGElement}
 */
function pointsGroup(points, fit) {
  const group = svgEl("g", { class: "cm-points" });
  const drawable = points.filter(
    (p) => Number.isFinite(p.lat) && Number.isFinite(p.lng),
  );
  group.append(...drawable.map((point) => pointEl(point, fit)));
  return group;
}

/**
 * Attribution, bottom-right, outside the zoomable viewport so it is always visible (ODbL requires it).
 * @param {string} text
 * @param {Fit} fit
 * @returns {{ link: SVGElement, label: SVGElement }}
 */
function attributionEl(text, fit) {
  const link = svgEl("a", {
    href: COPYRIGHT_URL,
    class: "cm-attribution-link",
  });
  const label = svgEl("text", {
    class: "cm-attribution",
    x: fmt(fit.width - ATTRIBUTION_INSET),
    y: fmt(fit.height - ATTRIBUTION_INSET),
    "text-anchor": "end",
  });
  label.textContent = text;
  link.append(label);
  return { link, label };
}

// --- Screen-size scaling ---

/**
 * SVG units scale with the drawing, but the attribution and the points should keep a fixed size in CSS pixels
 * whatever the map's displayed width and zoom. The scaler holds both and resizes them when either changes.
 * @param {SVGElement} viewport
 * @param {SVGElement} attribution
 * @param {number} radiusPx
 * @returns {Scaler}
 */
function createScaler(viewport, attribution, radiusPx) {
  let unitsPerPx = 1;
  let zoom = 1;
  const apply = () => {
    attribution.setAttribute("font-size", fmt(ATTRIBUTION_PX * unitsPerPx));
    const radius = fmt((radiusPx * unitsPerPx) / zoom);
    for (const circle of viewport.querySelectorAll("circle.pt")) {
      circle.setAttribute("r", radius);
    }
  };
  apply();
  return {
    setUnitsPerPx(value) {
      unitsPerPx = value;
      apply();
    },
    setZoom(value) {
      zoom = value;
      apply();
    },
  };
}

/**
 * Tell the scaler how many SVG units one CSS pixel is, now and whenever the map is resized.
 * @param {SVGSVGElement} svg
 * @param {number} width the SVG's viewBox width
 * @param {Scaler} scaler
 */
function watchSize(svg, width, scaler) {
  if (typeof ResizeObserver === "undefined") {
    return;
  }
  const observer = new ResizeObserver(() => {
    const shown = svg.getBoundingClientRect().width;
    if (shown > 0) {
      scaler.setUnitsPerPx(width / shown);
    }
  });
  observer.observe(svg);
}

// --- Zoom ---

/**
 * @param {SVGElement} viewport
 * @param {ViewBox} view
 */
function setViewBox(viewport, view) {
  viewport.setAttribute(
    "viewBox",
    [view.x, view.y, view.width, view.height].map(fmt).join(" "),
  );
}

/**
 * @param {string} text
 * @param {string} label
 * @param {() => void} onClick
 * @returns {HTMLButtonElement}
 */
function zoomButton(text, label, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = text;
  button.setAttribute("aria-label", label);
  button.addEventListener("click", onClick);
  return button;
}

/**
 * Wire +/- buttons, Ctrl/Cmd+wheel (and trackpad pinch), drag and two-finger pinch to the viewport's viewBox.
 * A plain wheel is left alone so the page still scrolls past the map.
 * @param {HTMLElement} frame
 * @param {SVGSVGElement} svg
 * @param {SVGElement} viewport
 * @param {{ full: ViewBox, scaler: Scaler, maxZoom: number }} config
 */
function enableZoom(frame, svg, viewport, config) {
  const { full, scaler, maxZoom } = config;
  let view = full;
  /** @param {ViewBox} next */
  const show = (next) => {
    view = next;
    setViewBox(viewport, view);
    scaler.setZoom(full.width / view.width);
  };
  /** @param {number} clientX @param {number} clientY */
  const toView = (clientX, clientY) => {
    const rect = svg.getBoundingClientRect();
    return {
      x: view.x + ((clientX - rect.left) / rect.width) * view.width,
      y: view.y + ((clientY - rect.top) / rect.height) * view.height,
    };
  };
  /** @param {number} factor @param {{ x: number, y: number }} focus */
  const zoomBy = (factor, focus) => {
    show(zoomViewBox(view, factor, focus, full, maxZoom));
  };
  const centre = () => ({
    x: view.x + view.width * HALF,
    y: view.y + view.height * HALF,
  });

  const controls = document.createElement("div");
  controls.className = "cm-zoom";
  controls.append(
    zoomButton("+", "Zoom in", () => {
      zoomBy(BUTTON_ZOOM_STEP, centre());
    }),
    zoomButton("−", "Zoom out", () => {
      zoomBy(1 / BUTTON_ZOOM_STEP, centre());
    }),
  );
  frame.append(controls);
  svg.classList.add("cm-zoomable");
  svg.addEventListener(
    "wheel",
    (event) => {
      if (!event.ctrlKey && !event.metaKey) {
        return;
      }
      event.preventDefault();
      zoomBy(
        event.deltaY < 0 ? WHEEL_ZOOM_STEP : 1 / WHEEL_ZOOM_STEP,
        toView(event.clientX, event.clientY),
      );
    },
    { passive: false },
  );
  enableDrag(svg, toView, (before, after) => {
    const factor =
      before.distance && after.distance ? after.distance / before.distance : 1;
    const moved = {
      ...view,
      x: view.x + before.x - after.x,
      y: view.y + before.y - after.y,
    };
    show(zoomViewBox(moved, factor, after, full, maxZoom));
  });
}

/**
 * Track pointers on the SVG and report each change of their centre and spread, in view box units.
 * @param {SVGSVGElement} svg
 * @param {(clientX: number, clientY: number) => { x: number, y: number }} toView
 * @param {(before: Gesture, after: Gesture) => void} onGesture
 */
function enableDrag(svg, toView, onGesture) {
  /** @type {Map<number, { x: number, y: number }>} */
  const pointers = new Map();
  const current = () =>
    gestureOf([...pointers.values()].map((p) => toView(p.x, p.y)));
  svg.addEventListener("pointerdown", (event) => {
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  });
  svg.addEventListener("pointermove", (event) => {
    if (!pointers.has(event.pointerId) || pointers.size > PINCH_POINTERS) {
      return;
    }
    const before = current();
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    onGesture(before, current());
  });
  /** @param {PointerEvent} event */
  const release = (event) => {
    pointers.delete(event.pointerId);
  };
  for (const type of /** @type {const} */ ([
    "pointerup",
    "pointercancel",
    "pointerleave",
  ])) {
    svg.addEventListener(type, release);
  }
}

// --- Public entry point ---

/**
 * Draw the basemap and points into container, replacing its contents.
 * @param {HTMLElement} container
 * @param {Basemap} basemap
 * @param {MapPoint[]} [points]
 * @param {MapOptions} [options]
 * @returns {HTMLDivElement} the map's frame element (class "citymap"), now the container's only child
 */
export function renderMap(container, basemap, points = [], options = {}) {
  const label = options.label ?? "Map";
  const fit = fitBBox(basemap.bbox, options.width ?? DEFAULT_WIDTH);
  const full = { x: 0, y: 0, width: fit.width, height: fit.height };
  const box = [0, 0, fit.width, fit.height].map(fmt).join(" ");

  const frame = document.createElement("div");
  frame.className = "citymap";
  const svg = /** @type {SVGSVGElement} */ (
    svgEl("svg", {
      class: "cm-svg",
      viewBox: box,
      role: "group",
      "aria-label": label,
    })
  );
  const viewport = svgEl("svg", {
    class: "cm-viewport",
    x: 0,
    y: 0,
    width: fmt(fit.width),
    height: fmt(fit.height),
    viewBox: box,
  });
  viewport.append(basemapGroup(basemap, fit, label), pointsGroup(points, fit));
  const attribution = attributionEl(basemap.attribution ?? ATTRIBUTION, fit);
  svg.append(viewport, attribution.link);
  frame.append(svg);
  const radiusPx = options.pointRadius ?? DEFAULT_POINT_RADIUS;
  const scaler = createScaler(viewport, attribution.label, radiusPx);
  watchSize(svg, fit.width, scaler);
  if (options.zoom) {
    enableZoom(frame, svg, viewport, {
      full,
      scaler,
      maxZoom: options.maxZoom ?? DEFAULT_MAX_ZOOM,
    });
  }
  container.replaceChildren(frame);
  return frame;
}
