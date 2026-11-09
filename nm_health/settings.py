# Copyright (c) 2026 nm_health contributors
"""Settings from config.toml at the repository root (no secrets live there)."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.toml"
DEFAULT_SITE_NAME = "Food Inspection History"
DEFAULT_WINDOW_DAYS = 365
DEFAULT_FEED_LOOKBACK_DAYS = 730


@dataclass(frozen=True)
class Settings:
    """Every setting the collector, ingest and site build read."""

    report_url: str
    user_agent: str
    timeout_seconds: int
    archive_dir: Path
    manifest: Path
    db: Path
    site_dir: Path
    cdx_url: str
    raw_url_template: str
    pdf_base_url: str
    site_name: str = DEFAULT_SITE_NAME
    indexable: bool = False
    # Only inspections this recent are collected and shown (archived PDFs are kept regardless).
    window_days: int = DEFAULT_WINDOW_DAYS
    feed_url: str = ""
    feed_categories: str = ""
    feed_bounds: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # lat1, lat2, lng1, lng2
    # Feed records are filtered by creation date, which can precede the inspection by months.
    feed_lookback_days: int = DEFAULT_FEED_LOOKBACK_DAYS
    feed_raw_dir: Path = ROOT / "data" / "feed" / "raw"


def load(path: Path = CONFIG_PATH) -> Settings:
    """Read config.toml; relative paths in it are relative to the file's own folder."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    base = path.resolve().parent
    source, paths, wayback, site, feed = data["source"], data["paths"], data["wayback"], data["site"], data["feed"]
    return Settings(
        report_url=str(source["report_url"]),
        user_agent=str(source["user_agent"]),
        timeout_seconds=int(source["timeout_seconds"]),
        archive_dir=base / str(paths["archive_dir"]),
        manifest=base / str(paths["manifest"]),
        db=base / str(paths["db"]),
        site_dir=base / str(paths["site_dir"]),
        cdx_url=str(wayback["cdx_url"]),
        raw_url_template=str(wayback["raw_url_template"]),
        pdf_base_url=str(site["pdf_base_url"]),
        site_name=str(site["name"]),
        indexable=bool(site["indexable"]),
        window_days=int(site["window_days"]),
        feed_url=str(feed["details_url"]),
        feed_categories=str(feed["categories"]),
        feed_bounds=(
            float(feed["lat1"]),
            float(feed["lat2"]),
            float(feed["lng1"]),
            float(feed["lng2"]),
        ),
        feed_lookback_days=int(feed["lookback_days"]),
        feed_raw_dir=base / str(feed["raw_dir"]),
    )
