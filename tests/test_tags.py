# Copyright (c) 2026 nm_health contributors
"""Tags come from what the inspector saw, not from rule boilerplate."""

import pytest

from nm_health.model import Violation
from nm_health.tags import tags_for

BOILERPLATE = (
    "If these areas are not kept clean, they may also provide harborage for insects, rodents, and other pests."
)


def v(category: str, item: str = "", observation: str = "", rule: str = BOILERPLATE) -> Violation:
    """A violation with rule boilerplate that mentions pests, so no tag may come from the rule."""
    return Violation(category=category, item=item, rule=rule, observation=observation)


@pytest.mark.parametrize(
    ("violation", "expected"),
    [
        pytest.param(
            v("Pest Control", "Removing Dead or Trapped Birds, Insects, Rodents and other Pest", "Observed pests."),
            ("pests", "pest_control"),
            id="dead_trapped_pests",
        ),
        pytest.param(
            v("Pest Control", "Controlling Pests, Inspection/Harborage", "Observed inadequate procedures."),
            ("pest_control",),
            id="pest_paperwork_only",
        ),
        pytest.param(
            v("Storage", "Food Storage", "Observed boxes on floor. Pest Type: Rodent droppings"),
            ("pests",),
            id="pest_type_field",
        ),
        pytest.param(
            v("S36 Insects, rodents, and animals not present", "6-501.111 Controlling Pests", "OBSERVED DEAD ROACHES."),
            ("pests", "pest_control"),
            id="legacy_dead_roaches",
        ),
        pytest.param(
            v(
                "S36 Insects, rodents, and animals not present",
                "6-202.15 Outer Openings, Protected",
                "OBSERVED DOOR GAP.",
            ),
            ("pest_control",),
            id="legacy_door_gap",
        ),
        pytest.param(
            v("Surface Condition", "Nonfood-Contact Surfaces", "Damaged due to coffee dropping on the cabinet doors."),
            (),
            id="coffee_dropping",
        ),
        pytest.param(
            v("Cooling", "Cooling Methods", "Observed food cooling without the necessary rate of heat transfer."),
            ("food_temperature",),
            id="rate_is_not_rat",
        ),
        pytest.param(
            v("Equipment Clean", "Clean to Sight and Touch", "Observed slicer with food debris."),
            (),
            id="boilerplate_ignored",
        ),
        pytest.param(
            v("Designated Areas", "Storage-Other Personal Care Items", "Car keys on the prep counter."),
            ("employee_items",),
            id="employee_items",
        ),
        pytest.param(
            v("Date Marking and Disposition", "Ready-To-Eat Time/Temperature Control for Safety Food, Date Marking"),
            ("date_marking",),
            id="tcs_phrase_not_temperature",
        ),
        pytest.param(
            v("Functionality and Accuracy", "Temperature Measuring Devices, Ambient Air and Water-Accuracy"),
            (),
            id="thermometer_not_food_temperature",
        ),
        pytest.param(v("Handwashing", "Handwashing Sinks, Accessibility"), ("handwashing",), id="handwashing"),
        pytest.param(v("Availability", "Cleaning Agents and Sanitizers, Availability"), ("sanitizer",), id="sanitizer"),
        pytest.param(v("Operations", "Valid Permit"), ("permit",), id="permit"),
        pytest.param(v("Training Records", "Food Handler Cards"), ("training",), id="training"),
    ],
)
def test_tags_for(violation: Violation, expected: tuple[str, ...]) -> None:
    """Each rule fires on its evidence and nothing else."""
    assert tags_for(violation) == expected
