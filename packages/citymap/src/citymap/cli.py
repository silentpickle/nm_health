# Copyright (c) 2026 nm_health contributors
"""Command line: `citymap build --bbox S,W,N,E --detail major --out map.geojson [--boundary NAME]`."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from citymap.bbox import BBox
from citymap.convert import convert, point_count
from citymap.detail import DETAILS
from citymap.overpass import build_query, fetch
from citymap.writer import dumps

BYTES_PER_KB = 1024


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="citymap", description="Build a small city basemap from OpenStreetMap.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="fetch OSM data from Overpass and write a basemap GeoJSON")
    build.add_argument("--bbox", required=True, type=BBox.parse, help="south,west,north,east in degrees")
    build.add_argument("--detail", choices=sorted(DETAILS), default="major", help="which roads to keep")
    build.add_argument("--out", required=True, type=Path, help="where to write the GeoJSON")
    build.add_argument("--boundary", help='name of an admin boundary to draw, e.g. "Albuquerque"')
    build.add_argument("--save-response", type=Path, help="also save the raw Overpass JSON here")
    build.add_argument("--from-response", type=Path, help="build from a saved Overpass JSON instead of the network")
    return parser


def _response(args: argparse.Namespace) -> dict[str, object]:
    """The Overpass response: read from --from-response, or fetched (one query) and optionally saved."""
    if args.from_response:
        return cast("dict[str, object]", json.loads(Path(args.from_response).read_text(encoding="utf-8")))
    query = build_query(args.bbox, DETAILS[args.detail].highways, args.boundary)
    response = fetch(query)
    if args.save_response:
        Path(args.save_response).write_text(json.dumps(response), encoding="utf-8")
    return response


def build(args: argparse.Namespace) -> int:
    """Run `citymap build`: fetch or read, convert, write, report the size."""
    detail = DETAILS[args.detail]
    collection = convert(_response(args), args.bbox, detail)
    text = dumps(collection)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    size_kb = len(text.encode()) / BYTES_PER_KB
    features, points = len(collection["features"]), point_count(collection)
    sys.stdout.write(f"wrote {out}: {features} features, {points} points, {size_kb:.0f} KB\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the `citymap` script."""
    args = _parser().parse_args(argv)
    return build(args)


if __name__ == "__main__":
    sys.exit(main())
