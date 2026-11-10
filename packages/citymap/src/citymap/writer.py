# Copyright (c) 2026 nm_health contributors
"""Serialise a basemap compactly: no spaces, one feature per line, so the file stays small and diffs stay readable."""

import json

from citymap.convert import Collection

COMPACT = (",", ":")


def _compact(value: object) -> str:
    return json.dumps(value, separators=COMPACT, ensure_ascii=False)


def dumps(collection: Collection) -> str:
    """The collection as GeoJSON text: a header line, one line per feature, a closing line."""
    header = (
        f'{{"type":"FeatureCollection","attribution":{_compact(collection["attribution"])},'
        f'"bbox":{_compact(collection["bbox"])},"features":['
    )
    features = ",\n".join(_compact(f) for f in collection["features"])
    return f"{header}\n{features}\n]}}\n"
