# Copyright (c) 2026 nm_health contributors
"""The labelled fields an inspector filled in, split out of an observation.

Observations read like "Observed pests allowed to accumulate in traps. Location: Back storage room Pest Type: Cockroach
Pest Condition: Dead". The labels run together with no separator, so the only reliable split is on the labels themselves:
one table of every label the city's forms print, matched case-sensitively as printed, longest first so "Pest Condition"
wins over "Condition". The leading sentence before the first label is the form's stock wording and is not a field.
"""

import re

Details = tuple[tuple[str, str], ...]

# Every label seen in the archive's observations, spelled and capitalized as printed. Data, not code: add a label here.
# Left out on purpose: "Current Status", which only appears where the next inspection's header leaked into the text.
LABELS: tuple[str, ...] = (
    "Activity",
    "Activity of the Food",
    "Actual Concentration",
    "Actual Temperature",
    "Additive or Component",
    "Alleged Material",
    "Ambient temperature",
    "Application Method",
    "Concentration",
    "Condition",
    "Condition of component",
    "Condition of the Location",
    "Condition of the equipment",
    "Condition of the items",
    "Container Type",
    "Corrective Action",
    "Current Policy",
    "Detergent being used",
    "Equipment",
    "Equipment Location",
    "Equipment Type",
    "Expiration Dates",
    "Food",
    "Food Item",
    "Food Items",
    "Food Items and Temperature",
    "Food Preparation Activity",
    "Food Temperature",
    "Food contact surface type",
    "Food/equipment Items",
    "Inappropriate Jewelry Observed",
    "Intended Use",
    "Items list",
    "Knowledge Tested",
    "Label Concentration",
    "Label Condition",
    "Label Temperature",
    "Location",
    "Location of the waste",
    "Manner",
    "Material",
    "Material Type",
    "Medication Name",
    "Method",
    "Number of Pests Present",
    "Number of eggs combined",
    "Observation",
    "Observed",
    "Packaged Food",
    "Pest Condition",
    "Pest Type",
    "Poisonous/Toxic Substance",
    "ROP Method",
    "Size",
    "Storage Method",
    "Storage method",
    "Surface",
    "Temperature",
    "Temperature measured",
    "Thermometer Location",
    "Time transpired",
    "Type",
    "Type of Device",
    "Type of Drink",
    "Type of Equipment",
    "Type of Food",
    "Type of Measuring Device",
    "Type of Sanitizer",
    "Type of equipment",
    "Type of items",
    "Use",
    "Utensil Type",
    "Working Container of Food",
)

# Longest first, so that at any position the fullest label wins ("Food Items and Temperature" over "Food Items").
LABEL_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(label) for label in sorted(LABELS, key=len, reverse=True)) + r")\s*:",
)
VALUE_TRIM = " \t\r\n.,;"


def details_for(observation: str) -> Details:
    """The observation's labelled fields as ordered (label, value) pairs; labels with no value are dropped."""
    matches = list(LABEL_PATTERN.finditer(observation))
    if not matches:
        return ()
    ends = [m.start() for m in matches[1:]] + [len(observation)]
    pairs = ((m.group(1), observation[m.end() : end].strip(VALUE_TRIM)) for m, end in zip(matches, ends, strict=True))
    return tuple((label, value) for label, value in pairs if value)


def detail(details: Details, label: str) -> str:
    """Every value given for one label, joined by "; " (empty when the inspector didn't fill it in)."""
    return "; ".join(value for name, value in details if name == label)
