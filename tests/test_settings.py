# Copyright (c) 2026 nm_health contributors
"""config.toml settings: what is read, and the bounds checked before anything runs."""

from dataclasses import replace
from pathlib import Path

import pytest

from nm_health.settings import DAYS_PER_WEEK, DEFAULT_STRIP_WEEKS, SettingsError, load
from tests.test_archive import make_settings

KEPT_WEEKS = DEFAULT_STRIP_WEEKS  # 365 days of data hold 52 whole weeks
QUARTER_WEEKS = 13


def test_strip_weeks_read_from_config() -> None:
    """The committed config.toml sets the strip to the full year of data kept."""
    assert load().strip_weeks == DEFAULT_STRIP_WEEKS


@pytest.mark.parametrize(
    "weeks",
    [
        pytest.param(1, id="one_week"),
        pytest.param(QUARTER_WEEKS, id="a_quarter"),
        pytest.param(KEPT_WEEKS, id="all_kept"),
    ],
)
def test_strip_weeks_in_bounds_accepted(tmp_path: Path, weeks: int) -> None:
    """Any span from one week to every whole week of data kept."""
    assert replace(make_settings(tmp_path), strip_weeks=weeks).strip_weeks == weeks


@pytest.mark.parametrize(
    "weeks",
    [
        pytest.param(0, id="no_weeks"),
        pytest.param(-1, id="negative_weeks"),
        pytest.param(KEPT_WEEKS + 1, id="past_window"),
    ],
)
def test_strip_weeks_out_of_bounds_rejected(tmp_path: Path, weeks: int) -> None:
    """An empty strip, or one reaching past the data kept, stops with the setting's name and its range."""
    with pytest.raises(SettingsError, match=rf"strip_weeks is {weeks}; it must be 1 to {KEPT_WEEKS}"):
        replace(make_settings(tmp_path), strip_weeks=weeks)


def test_strip_weeks_limit_follows_window(tmp_path: Path) -> None:
    """A shorter window_days lowers the most weeks allowed."""
    short_window = QUARTER_WEEKS * DAYS_PER_WEEK
    settings = replace(make_settings(tmp_path), window_days=short_window, strip_weeks=QUARTER_WEEKS)
    assert settings.strip_weeks == QUARTER_WEEKS
    with pytest.raises(SettingsError):
        replace(settings, strip_weeks=QUARTER_WEEKS + 1)
