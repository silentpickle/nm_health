# Copyright (c) 2026 nm_health contributors
"""Plain-language tags on violations, one small rule per tag.

Rules read the violation's headline (category + item) and the inspector's observation, never the rule boilerplate:
boilerplate such as "harborage for insects, rodents, and other pests" appears under ordinary cleaning violations.
"""

import re
from collections.abc import Callable
from dataclasses import replace

from nm_health.model import Violation

PEST_EVIDENCE = re.compile(
    r"\b(?:cockroach(?:es)?|roach(?:es)?|mouse|mice|rats?|gnats?|flies)\b|\b(?:rodent|mouse|rat|pest)s? droppings?\b|Pest Type:",
    re.IGNORECASE,
)
PEST_PRESENCE_ITEMS = re.compile(r"Removing Dead or Trapped|If Present: Treatment", re.IGNORECASE)
# Current reports file pest items under "Pest Control"; older ones under "S36 Insects, rodents, and animals not present",
# which also covers door gaps and screens (prevention, not evidence of pests).
PEST_CONTROL_CATEGORIES = re.compile(r"^Pest Control$|Insects, rodents,? and animals", re.IGNORECASE)
EMPLOYEE_ITEMS = re.compile(
    r"Personal Care Items|Personal Belongings|Employee Accommodations|Dressing Areas|Eating, Drinking,? or Using Tobacco",
    re.IGNORECASE,
)
FOOD_TEMPERATURE = re.compile(r"Temperature|Cold Holding|Hot Holding|Cooling|Reheating|Cooking", re.IGNORECASE)
NOT_FOOD_TEMPERATURE = re.compile(r"Measuring Device|Thermometer|Warewash|Temperature Logs", re.IGNORECASE)
# "Time/Temperature Control for Safety Food" names a class of food, not a temperature problem.
TCS_PHRASE = re.compile(r"Time/Temperature Control(?: for Safety)?", re.IGNORECASE)
HANDWASHING = re.compile(r"Hand ?wash|Hand Sink|Hands", re.IGNORECASE)
SANITIZER = re.compile(r"Saniti", re.IGNORECASE)
DATE_MARKING = re.compile(r"Date Marking", re.IGNORECASE)
PERMIT = re.compile(r"Valid Permit", re.IGNORECASE)
TRAINING = re.compile(r"Food Protection Manager|Food Handler", re.IGNORECASE)


def _headline(v: Violation) -> str:
    return f"{v.category} {v.item}"


def is_pests(v: Violation) -> bool:
    """Evidence of pests: named animals, droppings, or a pest-presence item."""
    return bool(PEST_EVIDENCE.search(v.observation) or PEST_PRESENCE_ITEMS.search(_headline(v)))


def is_pest_control(v: Violation) -> bool:
    """Pest prevention and control items: paperwork, device placement, door gaps, and pests themselves."""
    return bool(PEST_CONTROL_CATEGORIES.search(v.category.strip()))


def is_employee_items(v: Violation) -> bool:
    """Employee belongings, food or drink where they don't belong."""
    return bool(EMPLOYEE_ITEMS.search(_headline(v)))


def is_food_temperature(v: Violation) -> bool:
    """Food held, cooled or cooked at the wrong temperature (not thermometers or dish machines)."""
    headline = TCS_PHRASE.sub("", _headline(v))
    return bool(FOOD_TEMPERATURE.search(headline)) and not NOT_FOOD_TEMPERATURE.search(headline)


def is_handwashing(v: Violation) -> bool:
    """Hand sinks and handwashing."""
    return bool(HANDWASHING.search(_headline(v)))


def is_sanitizer(v: Violation) -> bool:
    """Sanitizing solutions and sanitizing of surfaces."""
    return bool(SANITIZER.search(_headline(v)))


def is_date_marking(v: Violation) -> bool:
    """Ready-to-eat food without dates."""
    return bool(DATE_MARKING.search(_headline(v)))


def is_permit(v: Violation) -> bool:
    """Operating without a valid permit."""
    return bool(PERMIT.search(_headline(v)))


def is_training(v: Violation) -> bool:
    """Missing certified manager or food handler cards."""
    return bool(TRAINING.search(_headline(v)))


TAG_RULES: tuple[tuple[str, Callable[[Violation], bool]], ...] = (
    ("pests", is_pests),
    ("pest_control", is_pest_control),
    ("employee_items", is_employee_items),
    ("food_temperature", is_food_temperature),
    ("handwashing", is_handwashing),
    ("sanitizer", is_sanitizer),
    ("date_marking", is_date_marking),
    ("permit", is_permit),
    ("training", is_training),
)


def tags_for(v: Violation) -> tuple[str, ...]:
    """Every tag whose rule matches, in TAG_RULES order."""
    return tuple(name for name, rule in TAG_RULES if rule(v))


def tagged(v: Violation) -> Violation:
    """The violation with its tags filled in."""
    return replace(v, tags=tags_for(v))
