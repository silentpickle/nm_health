# Copyright (c) 2026 nm_health contributors
"""``nm-health news add`` / ``news list``: what each prints, and that nothing it rejects reaches the links file."""

import json
import urllib.error
from dataclasses import replace
from pathlib import Path

from nm_health.news import load_links
from nm_health.news_commands import add_lines, archived_lines, list_lines
from nm_health.settings import Settings, load
from tests.test_archive import make_settings
from tests.test_news import write_manifest
from tests.test_news_capture import CAPTURE

COVERED_URL = "https://www.example.test/business/county-week/1"
GAP_URL = "https://www.example.test/business/gap-week/2"
GAP_LINES = ["Oct. 4-10", "GREEN", "Test Cafe, 100 Central SE (Oct. 6)", "RED", "NONE"]


def news_settings(tmp_path: Path) -> Settings:
    """Settings whose manifest (one county week, Nov 8-14 2026) and links file live in tmp_path."""
    settings = replace(make_settings(tmp_path), news_links=tmp_path / "links.jsonl", news_hosts=("www.example.test",))
    write_manifest(settings.manifest)
    return settings


def write_capture(path: Path, **change: object) -> Path:
    """A capture file: the test article, with fields changed."""
    path.write_text(json.dumps({**CAPTURE, **change}), encoding="utf-8")
    return path


def test_add_prints_each_file(tmp_path: Path) -> None:
    """Each file gets a line: recorded (with how much the county archive leaves usable), same again, or skipped."""
    settings = news_settings(tmp_path)
    covered = write_capture(tmp_path / "covered.json", url=COVERED_URL)
    gap = write_capture(tmp_path / "gap.json", url=GAP_URL, lines=GAP_LINES, published="2026-10-15")
    other_host = write_capture(tmp_path / "other.json", url="https://elsewhere.test/a/3")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    said = add_lines([covered, gap, covered, other_host, broken, tmp_path / "missing.json"], settings)
    assert said == [
        "NEW: example.test 2026-11-08..2026-11-14 Two businesses red-tagged",
        "  4 green, 1 yellow, 2 red; county PDF covers 7 of 7 days: not used (the county report wins)",
        "  warning: GREEN: no usable date in parentheses, skipped: No Date Diner, 400 Menaul NE",
        "  warning: RED: not a place line, skipped: For more information, visit the city's website.",
        "NEW: example.test 2026-10-04..2026-10-10 Two businesses red-tagged",
        "  1 green; no county PDF for these days: 1 of 1 entries usable",
        "same: example.test 2026-11-08..2026-11-14 Two businesses red-tagged",
        "  4 green, 1 yellow, 2 red; county PDF covers 7 of 7 days: not used (the county report wins)",
        "  warning: GREEN: no usable date in parentheses, skipped: No Date Diner, 400 Menaul NE",
        "  warning: RED: not a place line, skipped: For more information, visit the city's website.",
        "SKIPPED other.json: elsewhere.test is not in [news] hosts in config.toml",
        "SKIPPED broken.json: not a JSON text file (Expecting property name enclosed in double quotes: line 1 column 2 (char 1))",
        "SKIPPED missing.json: no such file",
    ]
    assert [json.loads(line)["url"] for line in settings.news_links.read_text(encoding="utf-8").splitlines()] == [
        GAP_URL,
        COVERED_URL,
    ]


def test_list_prints_links_and_totals(tmp_path: Path) -> None:
    """Oldest week first, each with its URL; then the usable total and the PDFs with no week on file."""
    settings = news_settings(tmp_path)
    covered = write_capture(tmp_path / "covered.json", url=COVERED_URL)
    gap = write_capture(tmp_path / "gap.json", url=GAP_URL, lines=GAP_LINES, published="2026-10-15")
    add_lines([covered, gap], settings)
    assert list_lines(settings) == [
        "2026-10-04..2026-10-10  example.test  1 green  no county PDF for these days: 1 of 1 entries usable",
        f"  {GAP_URL}",
        (
            "2026-11-08..2026-11-14  example.test  4 green, 1 yellow, 2 red  "
            "county PDF covers 7 of 7 days: not used (the county report wins)"
        ),
        f"  {COVERED_URL}",
        "2 news links; 1 of 8 entries usable (dated outside every county PDF's week)",
        "No county PDF and no news link yet: 2026-10-11..2026-11-07",
        "Archived PDFs with no week on file (their days aren't counted as covered): unknown-week_b.pdf",
    ]


def test_news_settings_read_from_config() -> None:
    """The committed config.toml allows the Albuquerque Journal and keeps links under data/news/."""
    settings = load()
    assert settings.news_hosts == ("www.abqjournal.com", "abqjournal.com")
    assert settings.news_links.parts[-3:] == ("data", "news", "links.jsonl")


def test_archived_copies_looked_up(tmp_path: Path) -> None:
    """Each link without a copy is looked up once: found, none yet, or no answer (left for next time); then saved."""
    settings = news_settings(tmp_path)
    add_lines([write_capture(tmp_path / f"{n}.json", url=f"{COVERED_URL}{n}") for n in range(3)], settings)
    answers = {f"{COVERED_URL}0": "https://web.archive.org/web/1/x", f"{COVERED_URL}1": ""}

    def lookup(url: str) -> str:
        if url not in answers:
            reason = "offline"
            raise urllib.error.URLError(reason)
        return answers[url]

    said = archived_lines(settings, lookup, pause=0)
    assert said == [
        "FOUND: https://web.archive.org/web/1/x",
        f"no copy yet: {COVERED_URL}1",
        f"no answer for {COVERED_URL}2 (<urlopen error offline>); try again later",
        "1 of 3 news links have an archived copy",
    ]
    assert [link.archived_url for link in load_links(settings.news_links)] == [
        "https://web.archive.org/web/1/x",
        "",
        "",
    ]
    assert archived_lines(settings, lambda _url: "again", pause=0)[0] == "FOUND: again"
