# Copyright (c) 2026 nm_health contributors
"""Pin the prototype parser's whole output on real reports (characterization test).

Regenerate only for a deliberate behaviour change, in that change's own commit:
    UPDATE_GOLDEN=1 uv run pytest tests/test_parser_golden.py
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from nm_health.ingest.parser import InspectionReportParser

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "data" / "archive"
GOLDEN = Path(__file__).resolve().parent / "golden"
PINNED_REPORTS = [
    "2026-09-20_2026-09-26_4526d9bed974.pdf",
    "2026-10-25_2026-10-31_0e0b9708501f.pdf",
]


def canonical(parsed: dict[str, Any]) -> dict[str, Any]:
    """The parser output with each establishment's inspections as indexes into the top-level list.

    They are the same objects in the parser's output; storing them once halves the file and loses nothing.
    """
    position = {id(insp): index for index, insp in enumerate(parsed["inspections"])}
    establishments = {
        slug: {**est, "inspections": [position[id(insp)] for insp in est["inspections"]]}
        for slug, est in parsed["establishments"].items()
    }
    return {**parsed, "establishments": establishments}


def golden_path(report: str) -> Path:
    """Where a report's pinned output lives."""
    return GOLDEN / report.replace(".pdf", ".json")


@pytest.mark.parametrize("report", PINNED_REPORTS)
def test_parser_output_unchanged(report: str) -> None:
    """The parser's whole output for each pinned report matches the committed snapshot."""
    actual = canonical(InspectionReportParser(ARCHIVE / report).parse())
    path = golden_path(report)
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(json.dumps(actual, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected
