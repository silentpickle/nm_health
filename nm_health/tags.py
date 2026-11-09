# Copyright (c) 2026 nm_health contributors
"""Plain-language tags on violations, one small rule per tag, and the pest evidence state.

Rules read the violation's headline (category + item), the inspector's observation and the labelled fields in it, never
the rule boilerplate: boilerplate such as "harborage for insects, rodents, and other pests" appears under ordinary
cleaning violations, and rule text such as "Instructed PIC to remove any dead pests" says nothing about what was seen.
"""

import re
from collections.abc import Callable
from dataclasses import replace

from nm_health.details import detail, details_for
from nm_health.model import Violation

# --- Pest types. A bare "rodents" is boilerplate ("entry of insects and rodents"), so rodents need a named animal,
# their droppings or activity, or the Pest Type field.
ROACHES = re.compile(r"\b(?:cock)?roach", re.IGNORECASE)
RODENT_EVIDENCE = re.compile(
    r"\b(?:mouse|mice|rats?)\b|\brodents?\s+(?:droppings?|feces|fecal|excrement|activity)\b",
    re.IGNORECASE,
)
RODENT_TYPE = re.compile(r"\b(?:rodents?|mouse|mice|rats?)\b", re.IGNORECASE)
# "fly" alone is too loose in prose ("fly lights", "fly strip"), so it counts only in the Pest Type field.
FLY_EVIDENCE = re.compile(r"\b(?:flies|gnats?)\b", re.IGNORECASE)
FLY_TYPE = re.compile(r"\b(?:fly|flies|gnats?)\b", re.IGNORECASE)
OTHER_PEST_TYPE = re.compile(
    r"\b(?:ants?|birds?|pigeons?|sparrows?|bats?|beetles?|weevils?|moths?|spiders?|crickets?|silverfish|"
    r"termites?|earwigs?|centipedes?|millipedes?|mites?|wasps?|bees?|hornets?|lizards?|geckos?|snakes?|"
    r"squirrels?|raccoons?|opossums?|skunks?|cats?|dogs?)\b",
    re.IGNORECASE,
)
PEST_TYPE_LABEL = "Pest Type"
# Items whose citation means pests were present. Legacy (2021-2024) S36 items don't qualify by name: "6-501.111
# Controlling Pests" there usually means "no licensed pest control service"; real sightings are caught by type.
PEST_PRESENCE_ITEMS = re.compile(r"Removing Dead or Trapped|If Present: Treatment", re.IGNORECASE)
# Current reports file pest items under "Pest Control"; older ones under the legacy S36 category.
PEST_CONTROL_CATEGORIES = re.compile(r"^Pest Control$|Insects, rodents,? and animals", re.IGNORECASE)

# --- Other tags.
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

# --- Pest evidence state. An instruction ("Instructed PIC to remove dead roaches.") is not an observation: the clause
# from the instruction verb to the end of its sentence is cut before the state is read.
INSTRUCTION_CLAUSE = re.compile(r"\b(?:instruct|discuss|advis|recommend)\w*\b[^.]*\.?", re.IGNORECASE)
# A pest killed, smashed or crushed during the inspection was alive when the inspector arrived.
LIVE = re.compile(r"\b(?:live|alive|living|crawling|active|killed|smashed|crushed|squashed)\b", re.IGNORECASE)
DEAD = re.compile(
    r"\b(?:dead|trapped)\b|\b(?:in|on)\s+(?:the\s+|a\s+)?(?:\w+\s+)?traps?\b|\bglue\s+(?:boards?|traps?)\b",
    re.IGNORECASE,
)
DROPPINGS = re.compile(r"\b(?:droppings?|feces|fecal|excrement|egg\s+cas(?:es|ings?))\b", re.IGNORECASE)
NOT_STATED = "not_stated"


def _headline(v: Violation) -> str:
    return f"{v.category} {v.item}"


def _pest_type(v: Violation) -> str:
    return detail(details_for(v.observation), PEST_TYPE_LABEL)


def is_roaches(v: Violation) -> bool:
    """Cockroaches named in the observation or its Pest Type field."""
    return bool(ROACHES.search(v.observation))


def is_rodents(v: Violation) -> bool:
    """Mice, rats, or rodent droppings; or a rodent named in the Pest Type field."""
    return bool(RODENT_EVIDENCE.search(v.observation) or RODENT_TYPE.search(_pest_type(v)))


def is_flies(v: Violation) -> bool:
    """Flies (house, fruit) or gnats."""
    return bool(FLY_EVIDENCE.search(v.observation) or FLY_TYPE.search(_pest_type(v)))


def is_other_pests(v: Violation) -> bool:
    """Any other pest (ants, birds, ...) named in the Pest Type field."""
    return bool(OTHER_PEST_TYPE.search(_pest_type(v)))


PEST_TYPE_RULES: tuple[tuple[str, Callable[[Violation], bool]], ...] = (
    ("roaches", is_roaches),
    ("rodents", is_rodents),
    ("flies", is_flies),
    ("other_pests", is_other_pests),
)


def is_pest_presence_item(v: Violation) -> bool:
    """A citation that means pests were present, whatever the observation says."""
    return bool(PEST_PRESENCE_ITEMS.search(_headline(v)))


def is_pests_unspecified(v: Violation) -> bool:
    """A pest-presence item where no pest type can be read."""
    return is_pest_presence_item(v) and not any(rule(v) for _, rule in PEST_TYPE_RULES)


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
    *PEST_TYPE_RULES,
    ("pests_unspecified", is_pests_unspecified),
    ("pest_control", is_pest_control),
    ("employee_items", is_employee_items),
    ("food_temperature", is_food_temperature),
    ("handwashing", is_handwashing),
    ("sanitizer", is_sanitizer),
    ("date_marking", is_date_marking),
    ("permit", is_permit),
    ("training", is_training),
)
PEST_TAGS = frozenset((*(name for name, _ in PEST_TYPE_RULES), "pests_unspecified"))


def _findings(v: Violation) -> str:
    """The observation with the inspector's instructions cut out: what was seen, not what was asked for."""
    return INSTRUCTION_CLAUSE.sub(" ", v.observation)


# Strongest evidence first: the first state whose pattern matches wins.
PEST_STATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("live", LIVE),
    ("dead", DEAD),
    ("droppings", DROPPINGS),
)
# The inspector's own fields outrank the free text: the form's stock "pests allowed to accumulate in traps" would
# otherwise read as dead when the Pest Type field says droppings.
STATE_LABELS = ("Pest Condition", "Pest Type")


def state_in(text: str) -> str | None:
    """The strongest pest state named in text."""
    return next((name for name, pattern in PEST_STATE_PATTERNS if pattern.search(text)), None)


def _labelled(v: Violation) -> str:
    """The Pest Condition and Pest Type fields the inspector filled in."""
    return " ".join(value for label, value in details_for(v.observation) if label in STATE_LABELS)


def tags_for(v: Violation) -> tuple[str, ...]:
    """Every tag whose rule matches, in TAG_RULES order."""
    return tuple(name for name, rule in TAG_RULES if rule(v))


def pest_state_for(v: Violation, tags: tuple[str, ...]) -> str | None:
    """The strongest pest evidence the inspector recorded; None when no pest tag applies."""
    if PEST_TAGS.isdisjoint(tags):
        return None
    return state_in(_labelled(v)) or state_in(_findings(v)) or NOT_STATED


def tagged(v: Violation) -> Violation:
    """The violation with its tags, pest state and labelled details filled in."""
    tags = tags_for(v)
    return replace(v, tags=tags, pest_state=pest_state_for(v, tags), details=details_for(v.observation))
