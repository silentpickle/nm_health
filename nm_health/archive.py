# Copyright (c) 2026 nm_health contributors
"""Keep every distinct weekly report PDF the city publishes.

Archiving never parses. A PDF the parser cannot read today is still kept, so a later parser can read it.
Files are named ``<week_start>_<week_end>_<sha256[:12]>.pdf``; an amended report for the same week has a new hash
and is kept beside the first one. ``manifest.jsonl`` records where and when each file was seen.
"""

import hashlib
import json
import re
import subprocess
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from nm_health.settings import Settings

PDF_MAGIC = b"%PDF-"
SHA_PREFIX_LEN = 12
ALLOWED_SCHEME = "https://"
FIRST_PAGE = "1"
UNKNOWN_WEEK = "unknown-week"
ARCHIVE_FILE_MODE = 0o644  # temp files start owner-only; archived reports are public record


class ArchiveError(Exception):
    """A download that is not a report PDF (often a Cloudflare challenge page)."""


@dataclass(frozen=True)
class Week:
    """The inspection week a report covers."""

    start: date
    end: date


@dataclass(frozen=True)
class Archived:
    """Outcome of archiving one PDF."""

    path: Path
    sha256: str
    is_new: bool


def download(url: str, user_agent: str, timeout_seconds: int) -> bytes:
    """Fetch url over https. HTTP errors propagate (a failed run is the alert)."""
    if not url.startswith(ALLOWED_SCHEME):
        msg = f"refusing non-https url: {url}"
        raise ArchiveError(msg)
    headers = {"User-Agent": user_agent, "Accept": "application/pdf,*/*"}
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 - https checked above
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - https checked above
        body: bytes = response.read()
    return body


def is_pdf(body: bytes) -> bool:
    """True when the bytes start like a PDF file."""
    return body.startswith(PDF_MAGIC)


def _dates_long(text: str) -> Week | None:
    """2025 onward: 'Week: October 25, 2026 to October 31, 2026'."""
    found = re.search(r"Week:\s*([A-Z][a-z]+ \d{1,2}, \d{4}) to ([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    if found is None:
        return None
    fmt = "%B %d, %Y"
    start = datetime.strptime(found[1], fmt).replace(tzinfo=UTC).date()
    end = datetime.strptime(found[2], fmt).replace(tzinfo=UTC).date()
    return Week(start, end)


def _dates_slashed(text: str) -> Week | None:
    """2024 and earlier: 'Inspections Performed 7/10/2021 - 7/16/2021'."""
    found = re.search(r"(\d{1,2}/\d{1,2}/\d{4}) - (\d{1,2}/\d{1,2}/\d{4})", text)
    if found is None:
        return None
    fmt = "%m/%d/%Y"
    start = datetime.strptime(found[1], fmt).replace(tzinfo=UTC).date()
    end = datetime.strptime(found[2], fmt).replace(tzinfo=UTC).date()
    return Week(start, end)


WEEK_FORMATS: tuple[Callable[[str], Week | None], ...] = (_dates_long, _dates_slashed)


def week_from_text(text: str) -> Week | None:
    """The report week stated in first-page text, trying each known format in turn."""
    flat = " ".join(text.split())
    for parse in WEEK_FORMATS:
        week = parse(flat)
        if week is not None:
            return week
    return None


def amended_from_text(text: str) -> str | None:
    """The date as the header prints it in 'Report Amended on 11/2/2026', or None when it isn't amended."""
    found = re.search(r"Report\s+amended\s+on\s*([\d/]+)", " ".join(text.split()), re.IGNORECASE)
    return found[1] if found else None


LETTERHEAD = "Environmental Health Department"


def has_letterhead(text: str) -> bool:
    """True when page 1 carries the city's 'Environmental Health Department' letterhead (2025-10 layout on)."""
    return LETTERHEAD.lower() in " ".join(text.split()).lower()


def first_page_text(pdf: Path) -> str:
    """Text of page 1 via poppler's pdftotext."""
    result = subprocess.run(
        ["pdftotext", "-f", FIRST_PAGE, "-l", FIRST_PAGE, "-layout", str(pdf), "-"],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


def archive_name(week: Week | None, seen_at: datetime, sha256: str) -> str:
    """File name for an archived PDF."""
    prefix = sha256[:SHA_PREFIX_LEN]
    if week is None:
        return f"{UNKNOWN_WEEK}_{seen_at.date().isoformat()}_{prefix}.pdf"
    return f"{week.start.isoformat()}_{week.end.isoformat()}_{prefix}.pdf"


def find_existing(archive_dir: Path, sha256: str) -> Path | None:
    """The archived file with this content, if there is one."""
    return next(iter(sorted(archive_dir.glob(f"*_{sha256[:SHA_PREFIX_LEN]}.pdf"))), None)


def _append_manifest(settings: Settings, entry: dict[str, str | int | None]) -> None:
    with settings.manifest.open("a", encoding="utf-8") as out:
        out.write(json.dumps(entry, sort_keys=True) + "\n")


def archive_bytes(body: bytes, source: str, seen_at: datetime, settings: Settings) -> Archived:
    """Save body under its week name unless the same bytes are already archived."""
    if not is_pdf(body):
        msg = f"not a PDF ({len(body)} bytes from {source}); first bytes: {body[: len(PDF_MAGIC) * 2]!r}"
        raise ArchiveError(msg)
    sha256 = hashlib.sha256(body).hexdigest()
    existing = find_existing(settings.archive_dir, sha256)
    if existing is not None:
        return Archived(existing, sha256, is_new=False)
    settings.archive_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=settings.archive_dir, suffix=".pdf", delete=False) as incoming:
        incoming.write(body)
    header = first_page_text(Path(incoming.name))
    week = week_from_text(header)
    final = settings.archive_dir / archive_name(week, seen_at, sha256)
    Path(incoming.name).replace(final)
    final.chmod(ARCHIVE_FILE_MODE)
    _append_manifest(
        settings,
        {
            "file": final.name,
            "sha256": sha256,
            "bytes": len(body),
            "week_start": week.start.isoformat() if week else None,
            "week_end": week.end.isoformat() if week else None,
            "source": source,
            "seen_at": seen_at.isoformat(),
            "amended_on": amended_from_text(header),
            "letterhead": has_letterhead(header),
        },
    )
    return Archived(final, sha256, is_new=True)


def archive_current(settings: Settings) -> Archived:
    """Download this week's report from the city and archive it if it is new."""
    body = download(settings.report_url, settings.user_agent, settings.timeout_seconds)
    return archive_bytes(body, settings.report_url, datetime.now(tz=UTC), settings)


def archive_file(pdf: Path, source: str, seen_at: datetime, settings: Settings) -> Archived:
    """Archive a PDF already on disk."""
    return archive_bytes(pdf.read_bytes(), source, seen_at, settings)
