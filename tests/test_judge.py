# Copyright (c) 2026 nm_health contributors
"""The typed second opinion: which closures qualify, the name rule, the agy answer's shape, and the saved cache."""

import json
import stat
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from nm_health.commands import _judge_one
from nm_health.judge import (
    BY_AGY,
    NOT_ASKED,
    JudgeError,
    Judgement,
    LongClosure,
    ask_agy,
    judge,
    load_cache,
    long_closures,
    parse_answer,
    prompt_for,
    ruled_out,
    save_cache,
    stale,
)
from nm_health.model import Inspection
from nm_health.viewmodel import Place, build_place
from tests.test_archive import make_settings

TODAY = date(2026, 11, 10)
MIN_DAYS = 14
CLOSED = "Closure Re-Inspection Required"
APPROVED = "Approved"
TIMEOUT = 30
GOOD_ANSWER = {
    "restaurant_only": "yes",
    "reason": "A sushi restaurant.",
    "operating_now": "closed",
    "evidence": "Listed as permanently closed on its map listing, Oct 2026.",
}


def visit(day: str, status: str, name: str = "OUMI SUSHI") -> Inspection:
    """One inspection of a place."""
    return Inspection(
        inspection_id=f"PT-{day}",
        date=day,
        kind="Routine Food Establishment Inspection",
        status=status,
        name=name,
        address="5112 LOMAS BLVD NE",
        permit_number=None,
        permit_type=None,
        report_file="",
        page=None,
        has_details=False,
    )


def place(*inspections: Inspection) -> Place:
    """A place from its inspections."""
    return build_place(inspections[0].name.lower().replace(" ", "-"), list(inspections))


def case(name: str = "OUMI SUSHI") -> LongClosure:
    """A place closed Nov 12, 2025 with nothing since."""
    (found,) = long_closures([place(visit("2025-11-12", CLOSED, name))], TODAY, MIN_DAYS)
    return found


def agy_output(answer: object) -> str:
    """What `agy --output-format json` prints."""
    return json.dumps({"status": "SUCCESS", "structured_output": answer})


# ---------- Which places ----------


def test_long_closures_need_an_open_closure_older_than_the_threshold() -> None:
    """Open and old: listed. Reopened, or closed only days ago: not."""
    old = place(visit("2025-11-12", CLOSED))
    reopened = place(visit("2025-11-12", CLOSED, "A"), visit("2025-11-20", APPROVED, "A"))
    recent = place(visit("2026-11-01", CLOSED, "B"))
    (found,) = long_closures([old, reopened, recent], TODAY, MIN_DAYS)
    assert (found.place.name, found.spell.start, found.days) == (
        "OUMI SUSHI",
        "2025-11-12",
        (TODAY - date(2025, 11, 12)).days,
    )


# ---------- The name rule ----------


@pytest.mark.parametrize(
    ("name", "word"),
    [
        pytest.param("DRURY INN & SUITES ALBUQUERQUE", "inn", id="hotel_inn"),
        pytest.param("TWINS ACADEMY", "academy", id="school_academy"),
        pytest.param("7-ELEVEN #1234", "7-eleven", id="convenience_7eleven"),
        pytest.param("OUMI SUSHI", None, id="restaurant_none"),
        pytest.param("INNOVATION KITCHEN", None, id="whole_word_only"),
    ],
)
def test_ruled_out_by_name(name: str, word: str | None) -> None:
    """Whole words in the name that say the place does more than serve food."""
    assert ruled_out(place(visit("2025-11-12", CLOSED, name))) == word


def test_judge_uses_the_rule_without_asking() -> None:
    """A ruled-out name is judged without a model call: no, with no second opinion."""
    found = judge(case("DRURY INN & SUITES ALBUQUERQUE"), "/nonexistent/agy", TIMEOUT, TODAY)
    assert (found.restaurant_only, found.operating_now, found.by) == ("no", NOT_ASKED, "rule: name says inn")


def test_prompt_names_the_place_and_the_closure() -> None:
    """The question carries the city's facts: name, address, inspection types, closure date."""
    text = prompt_for(case())
    assert "name: OUMI SUSHI" in text
    assert "address: 5112 LOMAS BLVD NE" in text
    assert "food-safety closure on 2025-11-12" in text


# ---------- The answer's shape ----------


def test_parse_answer_reads_the_structured_output() -> None:
    """A schema-shaped answer becomes a Judgement for this closure and day."""
    found = parse_answer(agy_output(GOOD_ANSWER), "2025-11-12", TODAY)
    assert found == Judgement(
        "2025-11-12", "yes", "A sushi restaurant.", "closed", GOOD_ANSWER["evidence"], BY_AGY, "2026-11-10"
    )


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(None, id="no_structured_output"),
        pytest.param({**GOOD_ANSWER, "extra": "x"}, id="extra_key"),
        pytest.param({k: v for k, v in GOOD_ANSWER.items() if k != "evidence"}, id="missing_key"),
        pytest.param({**GOOD_ANSWER, "restaurant_only": "probably"}, id="bad_restaurant_value"),
        pytest.param({**GOOD_ANSWER, "operating_now": "not asked"}, id="bad_operating_value"),
    ],
)
def test_parse_answer_rejects_anything_off_schema(answer: object) -> None:
    """Never a guess: an answer outside the schema is an error."""
    with pytest.raises(JudgeError):
        parse_answer(agy_output(answer), "2025-11-12", TODAY)


def fake_agy(tmp_path: Path, output: str, code: int = 0) -> str:
    """A stand-in agy that prints `output` and exits with `code`."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    script = tmp_path / "agy"
    script.write_text(f"#!/bin/sh\ncat <<'EOF'\n{output}\nEOF\nexit {code}\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_ask_agy_runs_the_command_and_checks_the_answer(tmp_path: Path) -> None:
    """The command's JSON is parsed and typed; a failing command is a JudgeError."""
    found = ask_agy(case(), fake_agy(tmp_path, agy_output(GOOD_ANSWER)), TIMEOUT, TODAY)
    assert (found.restaurant_only, found.operating_now) == ("yes", "closed")
    with pytest.raises(JudgeError, match="agy failed for OUMI SUSHI"):
        ask_agy(case(), fake_agy(tmp_path, "boom", code=1), TIMEOUT, TODAY)


# ---------- The cache ----------


def test_cache_round_trip_and_staleness(tmp_path: Path) -> None:
    """Saved and read back unchanged; a new closure makes the saved answer stale."""
    path = tmp_path / "judgements.json"
    assert load_cache(path) == {}
    saved = parse_answer(agy_output(GOOD_ANSWER), "2025-11-12", TODAY)
    save_cache(path, {"oumi-sushi": saved})
    cache = load_cache(path)
    assert cache == {"oumi-sushi": saved}
    assert not stale(cache, case())
    assert stale({"oumi-sushi": replace(saved, closure="2025-01-01")}, case())


def test_one_failed_place_is_reported_and_not_saved(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A model that doesn't answer leaves that place for the next run; a good answer is saved at once."""
    settings = replace(make_settings(tmp_path), judge_cache=tmp_path / "judgements.json")
    cache: dict[str, Judgement] = {}
    failing = replace(settings, judge_command=fake_agy(tmp_path / "bad", "boom", code=1))
    assert not _judge_one(case(), cache, failing, TODAY)
    assert cache == {}
    assert not settings.judge_cache.exists()
    assert "OUMI SUSHI: no answer (JudgeError" in capsys.readouterr().out
    working = replace(settings, judge_command=fake_agy(tmp_path / "good", agy_output(GOOD_ANSWER)))
    assert _judge_one(case(), cache, working, TODAY)
    assert load_cache(settings.judge_cache)[case().place.slug].operating_now == "closed"
