# citymap

A small, self-hosted city map: no Google Maps, no tile servers, nothing loaded from a third party in the visitor's
browser. Two halves that share only a GeoJSON file:

- **Builder** (Python, `citymap build`): one Overpass API query for a bounding box, turned into a compact basemap
  GeoJSON of major roads, the main river and water, and an optional city boundary.
- **Renderer** (`citymap.js` + `citymap.css`, plain ES module, zero dependencies): draws that basemap and your points
  as inline SVG.

citymap knows nothing about what the points mean. Any project (any language) that can write
`[{lat, lng, kind, label, href}]` can use it.

## Attribution (required)

The basemap is derived from OpenStreetMap data, licensed under the
[Open Database License (ODbL)](https://www.openstreetmap.org/copyright). Every map must show
**"© OpenStreetMap contributors (ODbL)"**. The builder writes it into the GeoJSON (`"attribution"`), and the renderer
always draws it bottom-right, linked to the OSM copyright page, outside the zoomable area so it never scrolls away.
Do not hide it with CSS. If you redistribute the GeoJSON itself, keep the `attribution` field and note the ODbL.

## Builder

Python 3.12+, managed with [uv](https://docs.astral.sh/uv/). No runtime dependencies (the geometry is pure Python).

```sh
cd packages/citymap
uv sync
uv run citymap build --bbox 34.94,-106.89,35.22,-106.46 --detail major --boundary Albuquerque \
    --out data/albuquerque.geojson
```

| Flag | Meaning |
| --- | --- |
| `--bbox S,W,N,E` | Required. South, west, north, east in degrees (the Overpass order). |
| `--detail major\|medium` | `major` (default): motorway, trunk, primary. `medium` adds secondary roads. |
| `--out PATH` | Required. Where to write the GeoJSON (parent folders are created). |
| `--boundary NAME` | Also draw the admin boundary relation with this exact `name`, e.g. `Albuquerque`. |
| `--save-response PATH` | Also save the raw Overpass JSON, to rebuild later without the network. |
| `--from-response PATH` | Build from a saved Overpass JSON instead of querying Overpass. |

What it does:

1. **One POST** to `https://overpass-api.de/api/interpreter` with the User-Agent `citymap/0.1` (nothing personal).
   HTTP 429 and 504 are retried politely (wait 30 s, 60 s, 120 s; four attempts in all). Any other failure stops the
   build with an `OverpassError` that names the cause.
2. **Keeps** roads of the chosen detail, `waterway=river` lines, `natural=water` areas, and the named boundary.
   Dry or man-made water is dropped: anything `intermittent=yes` or `seasonal=yes` (arroyos in arid cities, which
   OSM tags as rivers) and `water=basin|ditch|drain|wastewater`.
3. **Joins** ways that share endpoints (OSM splits one road into many ways), **clips** to the bbox (rivers and
   riverbanks can run far beyond it), **simplifies** with Ramer-Douglas-Peucker (tolerance in ground metres: 10 m at
   `major`, 6 m at `medium`), **rounds** to 5 decimals (about 1 m), and **drops** pieces shorter than 60 m (40 m) and
   water smaller than 4 ha (2 ha).
4. **Writes** a GeoJSON FeatureCollection, one feature per line so diffs stay readable.

### Output format

```json
{"type":"FeatureCollection","attribution":"© OpenStreetMap contributors (ODbL)","bbox":[-106.89,34.94,-106.46,35.22],"features":[
{"type":"Feature","properties":{"kind":"road_major","name":"I 25"},"geometry":{"type":"MultiLineString","coordinates":[...]}},
...
]}
```

- `bbox` is in GeoJSON order: `[west, south, east, north]` (the CLI takes Overpass order, south first).
- `properties.kind` is one of `road_major`, `road_medium`, `river`, `water`, `boundary`; `properties.name` is present
  when OSM has a `name` (or, for roads, a `ref` such as `I 25`).
- Lines are one `MultiLineString` per (kind, name); water is one `MultiPolygon` per name (outer rings only: river
  islands are filled, which is invisible at city scale). Features are sorted in drawing order.

### Regenerating `data/albuquerque.geojson`

```sh
cd packages/citymap
uv run citymap build --bbox 34.94,-106.89,35.22,-106.46 --detail major --boundary Albuquerque \
    --out data/albuquerque.geojson
uv run pytest tests/test_data.py   # still under 300 KB, attributed, rounded, inside the bbox
```

The bbox is slightly wider (by 0.01° east and west) than the first-planned `34.94,-106.88,35.22,-106.47`, because the
city limits reach -106.8822 and -106.4714. The committed file is about 66 KB (55 features, about 2,700 points).
OSM changes; expect small diffs when you rebuild.

## Renderer

```html
<link rel="stylesheet" href="citymap.css" />
<div id="map"></div>
<script type="module">
  import { renderMap } from "./citymap.js";

  const basemap = await (await fetch("albuquerque.geojson")).json();
  renderMap(
    document.getElementById("map"),
    basemap,
    [
      { lat: 35.0844, lng: -106.6504, kind: "pass", label: "Cafe One, passed", href: "/places/cafe-one/" },
      { lat: 35.0853, lng: -106.6056, kind: "fail", label: "Diner Two, failed" },
    ],
    { zoom: true, label: "Albuquerque" },
  );
</script>
```

`example.html` is a working page: serve this folder (`python3 -m http.server`) and open `/example.html`.

### `renderMap(container, basemap, points = [], options = {})`

Replaces the contents of `container` with the map and returns the new frame element (`div.citymap`).

- `basemap`: the GeoJSON FeatureCollection from the builder (needs `bbox`; `attribution` falls back to the OSM line).
  `LineString`, `MultiLineString`, `Polygon` and `MultiPolygon` geometries are drawn; features of other kinds are
  skipped.
- `points`: `[{ lat, lng, kind?, label?, href? }]`. Each becomes `<circle class="pt pt-<kind>">` with a `<title>`.
  With `href` it is wrapped in `<a href aria-label="<label>">` (keyboard focusable); without, the circle itself gets
  `role="img"` and `aria-label`. Any `kind` string works (non-word characters become `-`; missing is `default`).
  Points with a non-finite `lat`/`lng` are skipped.
- `options`:
  - `zoom` (default `false`): +/- buttons, Ctrl/Cmd+wheel or trackpad pinch, touch pinch, and drag to pan, all by
    changing the viewBox. A plain wheel still scrolls the page. With zoom on, the map sets `touch-action: none`.
  - `label` (default `"Map"`): accessible name of the map.
  - `pointRadius` (default `5`): point radius in CSS pixels, kept at any map size and zoom.
  - `maxZoom` (default `8`).
  - `width` (default `1000`): width of the SVG coordinate space; the SVG itself is fluid (`width: 100%`).

Projection: equirectangular, longitude scaled by cos(mid-latitude) so distances are true in both directions at city
scale, fitted to the basemap bbox. Layers are drawn water, river, roads (medium under major), boundary, then points.

Structure, for styling and tests:

```
div.citymap
  svg.cm-svg[role=group][aria-label]
    svg.cm-viewport                       (the zoomed viewBox)
      g.cm-basemap[role=img][aria-label]  (with a <title>)
        g.cm-layer.cm-layer-water  > path.cm-feature.cm-water
        g.cm-layer.cm-layer-river  > path.cm-feature.cm-river
        g.cm-layer.cm-layer-roads  > path.cm-feature.cm-road_medium, path.cm-feature.cm-road_major
        g.cm-layer.cm-layer-boundary > path.cm-feature.cm-boundary
      g.cm-points > a.cm-point-link > circle.pt.pt-<kind>   (or a bare circle.pt without href)
    a.cm-attribution-link > text.cm-attribution
  div.cm-zoom > button × 2                (only with zoom)
```

Feature paths carry `data-name` when the feature has a name.

### Pure helpers (exported)

`fitBBox(bbox, width)` → `{ width, height, project(lng, lat) → [x, y] }`; `geometryPath(geometry, project)` → SVG
path data; `zoomViewBox(view, factor, focus, full, maxZoom)`; `clampViewBox(view, full)`; `gestureOf(pointers)`;
`kindClass(kind)`; `ATTRIBUTION`.

### Styling

Include `citymap.css`. Every colour and width reads a public custom property, so a host page overrides it by setting
the property anywhere above the map (light and dark defaults switch with `prefers-color-scheme`):

| Property | Default use |
| --- | --- |
| `--cm-bg` | map background, attribution halo |
| `--cm-water` | water fill |
| `--cm-river`, `--cm-river-width` | river line |
| `--cm-road-major`, `--cm-road-major-width` | motorway, trunk, primary |
| `--cm-road-medium`, `--cm-road-medium-width` | secondary |
| `--cm-boundary`, `--cm-boundary-width` | city boundary (dashed) |
| `--cm-text` | attribution text |
| `--cm-point`, `--cm-point-stroke`, `--cm-point-stroke-width` | points |
| `--cm-focus` | focused or hovered point, focused zoom button |
| `--cm-control-bg`, `--cm-control-fg`, `--cm-control-border` | zoom buttons |

Colour your own point kinds by class, e.g. `.citymap .pt-fail { --cm-point: #c92a2a; }`. Line widths stay in screen
pixels at any zoom (`vector-effect: non-scaling-stroke`).

## Development

```sh
cd packages/citymap
uv sync && npm ci
scripts/checks.sh
```

`scripts/checks.sh` runs ruff (all rules), ruff format, mypy `--strict`, the complexity ratchet, shellcheck, pytest,
then Prettier, ESLint (typescript-eslint strict, complexity 15, depth 2, no magic numbers), `tsc` (strict, checkJs)
and `node --test`. Tests never touch the network: the Overpass conversion runs from `tests/fixtures/`.
