// Copyright (c) 2026 nm_health contributors
// Pure helpers of the renderer: projection, bbox fit, path data, zoom maths. No DOM needed.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  clampViewBox,
  fitBBox,
  geometryPath,
  gestureOf,
  kindClass,
  zoomViewBox,
} from "../citymap.js";

/** @typedef {import("../citymap.js").BBox} BBox */
/** @typedef {import("../citymap.js").Basemap} Basemap */

const WIDTH = 1000;
const HALF_WIDTH = 500;
const EAST = 2;
const NORTH = 0.5;
const SOUTH = -0.5;
const EQUATOR_BOX = /** @type {BBox} */ ([0, SOUTH, EAST, NORTH]);
const SIXTY_SOUTH = 59.5;
const SIXTY_NORTH = 60.5;
const SIXTY_WEST = 10;
const SIXTY_EAST = 11;
const SIXTY_NORTH_BOX = /** @type {BBox} */ ([
  SIXTY_WEST,
  SIXTY_SOUTH,
  SIXTY_EAST,
  SIXTY_NORTH,
]);
const COS_60 = 0.5;
const TOLERANCE = 1e-9;
const MAX_ZOOM = 8;
const ZOOM_IN = 2;
const QUARTER = 250;
const THIRDS = 3;

/**
 * @param {number} actual
 * @param {number} expected
 */
function near(actual, expected) {
  assert.ok(
    Math.abs(actual - expected) < TOLERANCE,
    `${String(actual)} is not ${String(expected)}`,
  );
}

test("fit_equator_box: height follows the bbox aspect at the equator", () => {
  const fit = fitBBox(EQUATOR_BOX, WIDTH);
  near(fit.width, WIDTH);
  near(fit.height, HALF_WIDTH);
});

test("fit_corners: north-west maps to the origin and south-east to the far corner", () => {
  const fit = fitBBox(EQUATOR_BOX, WIDTH);
  const [x0, y0] = fit.project(0, NORTH);
  const [x1, y1] = fit.project(EAST, SOUTH);
  near(x0, 0);
  near(y0, 0);
  near(x1, fit.width);
  near(y1, fit.height);
});

test("fit_cos_correction: a degree of longitude at 60N is half a degree of latitude", () => {
  const fit = fitBBox(SIXTY_NORTH_BOX, WIDTH);
  near(fit.height, WIDTH / COS_60);
});

test("fit_rejects_empty_box: inverted or empty bboxes throw", () => {
  assert.throws(() => fitBBox([1, 0, 1, 1], WIDTH), RangeError);
  assert.throws(() => fitBBox([0, 1, 1, 0], WIDTH), RangeError);
});

test("fit_albuquerque: the committed basemap fits wider than tall, like the city box", () => {
  const url = new URL("../data/albuquerque.geojson", import.meta.url);
  /** @type {unknown} */
  const parsed = JSON.parse(readFileSync(url, "utf8"));
  const basemap = /** @type {Basemap} */ (parsed);
  const fit = fitBBox(basemap.bbox, WIDTH);
  assert.ok(fit.height > 0 && fit.height < fit.width);
  assert.ok(basemap.features.length > 0);
});

test("path_line_and_polygon: lines stay open, polygon rings close with Z", () => {
  const fit = fitBBox(EQUATOR_BOX, WIDTH);
  const line = geometryPath(
    {
      type: "LineString",
      coordinates: [
        [0, NORTH],
        [EAST, SOUTH],
      ],
    },
    fit.project,
  );
  assert.equal(line, "M0 0L1000 500");
  const polygon = geometryPath(
    {
      type: "Polygon",
      coordinates: [
        [
          [0, NORTH],
          [1, NORTH],
          [1, SOUTH],
          [0, NORTH],
        ],
      ],
    },
    fit.project,
  );
  assert.equal(polygon, "M0 0L500 0L500 500L0 0Z");
});

test("path_multi_geometries: every part becomes its own subpath", () => {
  const fit = fitBBox(EQUATOR_BOX, WIDTH);
  const lines = geometryPath(
    {
      type: "MultiLineString",
      coordinates: [
        [
          [0, NORTH],
          [1, NORTH],
        ],
        [
          [1, SOUTH],
          [EAST, SOUTH],
        ],
      ],
    },
    fit.project,
  );
  assert.equal(lines, "M0 0L500 0M500 500L1000 500");
  const polygons = geometryPath(
    {
      type: "MultiPolygon",
      coordinates: [
        [
          [
            [0, NORTH],
            [1, NORTH],
            [0, NORTH],
          ],
        ],
        [
          [
            [1, SOUTH],
            [EAST, SOUTH],
            [1, SOUTH],
          ],
        ],
      ],
    },
    fit.project,
  );
  assert.equal(polygons, "M0 0L500 0L0 0ZM500 500L1000 500L500 500Z");
});

test("path_rounds_to_one_decimal: path numbers are short", () => {
  const third = 1 / THIRDS;
  const fit = fitBBox(EQUATOR_BOX, WIDTH);
  const path = geometryPath(
    {
      type: "LineString",
      coordinates: [
        [third, NORTH],
        [EAST, SOUTH],
      ],
    },
    fit.project,
  );
  assert.equal(path, "M166.7 0L1000 500");
});

const FULL = { x: 0, y: 0, width: WIDTH, height: HALF_WIDTH };

test("zoom_keeps_focus_fixed: the point under the cursor stays put", () => {
  const focus = { x: QUARTER, y: QUARTER };
  const view = zoomViewBox(FULL, ZOOM_IN, focus, FULL);
  near(view.width, HALF_WIDTH);
  near(view.height, QUARTER);
  near((focus.x - view.x) / view.width, (focus.x - FULL.x) / FULL.width);
  near((focus.y - view.y) / view.height, (focus.y - FULL.y) / FULL.height);
});

test("zoom_max_limit: zoom stops at maxZoom", () => {
  const huge = 1000;
  const view = zoomViewBox(FULL, huge, { x: 0, y: 0 }, FULL, MAX_ZOOM);
  near(view.width, WIDTH / MAX_ZOOM);
});

test("zoom_out_limit: zooming out stops at the full map", () => {
  const view = zoomViewBox(
    FULL,
    1 / ZOOM_IN,
    { x: HALF_WIDTH, y: QUARTER },
    FULL,
  );
  assert.deepEqual(view, FULL);
});

test("clamp_pans_back_inside: a view pushed past an edge comes back", () => {
  const view = clampViewBox(
    { x: -100, y: 400, width: HALF_WIDTH, height: QUARTER },
    FULL,
  );
  assert.deepEqual(view, {
    x: 0,
    y: QUARTER,
    width: HALF_WIDTH,
    height: QUARTER,
  });
});

test("gesture_two_pointers: centre and spread of a pinch", () => {
  const spread = 3;
  const depth = 4;
  const centreX = 1.5;
  const distance = 5;
  const gesture = gestureOf([
    { x: 0, y: 0 },
    { x: spread, y: depth },
  ]);
  assert.deepEqual(gesture, { x: centreX, y: depth / ZOOM_IN, distance });
});

test("gesture_one_pointer: a drag has no spread", () => {
  assert.deepEqual(gestureOf([{ x: 1, y: ZOOM_IN }]), {
    x: 1,
    y: ZOOM_IN,
    distance: 0,
  });
});

test("kind_class_sanitised: any kind string becomes a valid class suffix", () => {
  assert.equal(kindClass("road_major"), "road_major");
  assert.equal(kindClass("needs work!"), "needs-work-");
  assert.equal(kindClass(""), "default");
});
