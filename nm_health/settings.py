# Copyright (c) 2026 nm_health contributors
"""Settings from config.toml at the repository root (no secrets live there)."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.toml"


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


def load(path: Path = CONFIG_PATH) -> Settings:
    """Read config.toml; relative paths in it are relative to the file's own folder."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    base = path.resolve().parent
    source, paths, wayback, site = data["source"], data["paths"], data["wayback"], data["site"]
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
    )
