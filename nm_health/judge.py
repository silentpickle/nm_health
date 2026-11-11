# Copyright (c) 2026 nm_health contributors
"""A typed second opinion on places whose closure has been in force a long time.

A closure with no reopening inspection on record for weeks usually means the reopening is missing from our records
(corrective-action visits are only in weekly reports we may not hold), and sometimes that the business shut for good.
For each such place this asks two questions, with typed answers: is its only trade food service (restaurant-only),
and, from a web check, is it operating now. Names that say otherwise (hotel, school, gas station...) are ruled out
without asking. The model is `agy` in print mode with a JSON schema, so it needs the user's login: run
`nm-health judge` locally and commit `[judge] cache`. Nothing here reaches the public site; the audit lists it.
"""

import json
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal, get_args

from nm_health.model import Inspection
from nm_health.signals import ClosedSpell
from nm_health.viewmodel import Place

RestaurantOnly = Literal["yes", "no", "unsure"]
Operating = Literal["operating", "closed", "unknown", "not asked"]
AGY_ANSWERS: tuple[str, ...] = ("operating", "closed", "unknown")
BY_AGY = "agy"
PROCESS_GRACE_SECONDS = 60  # agy's own print timeout ends the turn first; this only catches a hang
NOT_ASKED: Operating = "not asked"
# Names that say the place does more than serve food. Matched as whole words, case-insensitively.
NOT_FOOD_ONLY_WORDS = (
    "hotel",
    "inn",
    "suites",
    "motel",
    "lodge",
    "resort",
    "casino",
    "school",
    "academy",
    "elementary",
    "church",
    "market",
    "grocery",
    "grocer",
    "supermarket",
    "store",
    "mart",
    "gas",
    "fuel",
    "7-eleven",
    "7-11",
    "circle k",
    "allsup's",
    "maverik",
    "speedway",
    "quick track",
    "walmart",
    "target",
    "costco",
    "walgreens",
    "cvs",
    "dollar",
    "hospital",
    "nursing",
    "rehab",
    "assisted living",
    "senior",
    "child development",
    "daycare",
    "cinema",
    "theater",
    "bowl",
    "golf",
    "airport",
)
REQUIRED = ("restaurant_only", "reason", "operating_now", "evidence")
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": list(REQUIRED),
    "properties": {
        "restaurant_only": {"type": "string", "enum": list(get_args(RestaurantOnly))},
        "reason": {"type": "string"},
        "operating_now": {"type": "string", "enum": list(AGY_ANSWERS)},
        "evidence": {"type": "string"},
    },
}
PROMPT = """A business in Albuquerque, New Mexico, from the city's food-inspection records:
name: {name}{legal}
address: {address}
inspection types: {kinds}
The city recorded a food-safety closure on {closed} and no reopening inspection appears in the records we hold.

1. Is this business's only trade food service (a restaurant, cafe, bar, bakery or food truck), as opposed to a hotel,
   store, gas station, school, church, care home or other business that also serves food? Answer yes, no or unsure,
   with a one-sentence reason.
2. Search the web for this business at this address. Is it operating today? Answer operating, closed (permanently or
   temporarily) or unknown, and give the evidence: what you found, where, and how recent it is. Say unknown rather
   than guess.

Use at most three web searches in all, then answer. If they don't settle a question, answer unsure or unknown."""


class JudgeError(Exception):
    """The model could not be asked, or its answer did not fit the schema."""


@dataclass(frozen=True)
class Judgement:
    """A restaurant-only verdict and a second opinion on whether the place operates now."""

    closure: str  # the closure start this was judged for; a new closure is judged again
    restaurant_only: RestaurantOnly
    reason: str
    operating_now: Operating
    evidence: str
    by: str  # "agy", or "rule: name says <word>"
    checked: str  # ISO date


@dataclass(frozen=True)
class LongClosure:
    """A place whose latest closure has no reopening inspection on record."""

    place: Place
    spell: ClosedSpell
    days: int


# ---------- Which places ----------


def long_closures(places: list[Place], today: date, min_days: int) -> list[LongClosure]:
    """Places whose latest closure has had no reopening inspection on record for at least `min_days`."""
    found = []
    for place in places:
        spell = place.spells[-1] if place.spells else None
        if spell is None or spell.end is not None:
            continue
        days = (today - date.fromisoformat(spell.start)).days
        if days >= min_days:
            found.append(LongClosure(place, spell, days))
    return sorted(found, key=lambda c: c.days, reverse=True)


# ---------- The rule ----------


def _word(word: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", re.IGNORECASE)


NAME_RULES = tuple((word, _word(word)) for word in NOT_FOOD_ONLY_WORDS)


def ruled_out(place: Place) -> str | None:
    """The word in the place's name that says it does more than serve food, if any."""
    names = " ".join(n for n in (place.name, place.legal_name) if n)
    return next((word for word, pattern in NAME_RULES if pattern.search(names)), None)


# ---------- Asking the model ----------


def _kinds(inspections: tuple[Inspection, ...]) -> str:
    return ", ".join(sorted({i.kind for i in inspections}))


def prompt_for(case: LongClosure) -> str:
    """The question for one place."""
    place = case.place
    legal = f"\nlegal name: {place.legal_name}" if place.legal_name else ""
    return PROMPT.format(
        name=place.name, legal=legal, address=place.address, kinds=_kinds(place.inspections), closed=case.spell.start
    )


def parse_answer(output: str, closure: str, today: date) -> Judgement:
    """Read agy's JSON output; anything outside the schema is an error, never a guess."""
    answer = json.loads(output).get("structured_output")
    if not isinstance(answer, dict) or set(answer) != set(REQUIRED):
        msg = f"agy answer does not fit the schema: {output[:200]}"
        raise JudgeError(msg)
    restaurant, operating = answer["restaurant_only"], answer["operating_now"]
    if restaurant not in get_args(RestaurantOnly) or operating not in AGY_ANSWERS:
        msg = f"agy answer outside the allowed values: {answer}"
        raise JudgeError(msg)
    return Judgement(
        closure, restaurant, str(answer["reason"]), operating, str(answer["evidence"]), BY_AGY, today.isoformat()
    )


def ask_agy(case: LongClosure, command: str, timeout_seconds: int, today: date) -> Judgement:
    """One agy call in print mode, plan mode and a sandbox, from an empty folder; its answer checked by type."""
    args = [
        command,
        *("--mode", "plan", "--sandbox", "--output-format", "json"),
        *("--print-timeout", f"{timeout_seconds}s", "--json-schema", json.dumps(SCHEMA)),
    ]
    with tempfile.TemporaryDirectory() as empty:
        try:
            done = subprocess.run(
                [*args, "-p", prompt_for(case)],
                capture_output=True,
                text=True,
                timeout=timeout_seconds + PROCESS_GRACE_SECONDS,
                check=True,
                cwd=empty,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            msg = f"agy failed for {case.place.name}: {error}"
            raise JudgeError(msg) from error
    return parse_answer(done.stdout, case.spell.start, today)


def judge(case: LongClosure, command: str, timeout_seconds: int, today: date) -> Judgement:
    """The rule when the name rules the place out (no model call), else agy."""
    word = ruled_out(case.place)
    if word is None:
        return ask_agy(case, command, timeout_seconds, today)
    reason = f"The name says it does more than serve food ({word})."
    return Judgement(case.spell.start, "no", reason, NOT_ASKED, "", f"rule: name says {word}", today.isoformat())


# ---------- The committed cache ----------


def load_cache(path: Path) -> dict[str, Judgement]:
    """Saved judgements by place slug; empty when none are saved yet."""
    if not path.exists():
        return {}
    raw: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return {slug: Judgement(**fields) for slug, fields in raw.items()}


def save_cache(path: Path, judgements: dict[str, Judgement]) -> None:
    """Write the judgements, sorted, so the committed file diffs cleanly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {slug: asdict(j) for slug, j in sorted(judgements.items())}
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def stale(cache: dict[str, Judgement], case: LongClosure) -> bool:
    """No judgement yet for this place, or the one saved was for an earlier closure."""
    saved = cache.get(case.place.slug)
    return saved is None or saved.closure != case.spell.start
