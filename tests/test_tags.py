# Copyright (c) 2026 nm_health contributors
"""Tags come from what the inspector saw, not from rule boilerplate."""

import pytest

from nm_health.model import Violation
from nm_health.tags import tagged, tags_for

BOILERPLATE = (
    "If these areas are not kept clean, they may also provide harborage for insects, rodents, and other pests."
)


PEST_ITEM = "Removing Dead or Trapped Birds, Insects, Rodents and other Pest"
TREATMENT_ITEM = "Controlling Pests, If Present: Treatment"
LEGACY_CATEGORY = "S36 Insects, rodents, and animals not present"


def v(category: str, item: str = "", observation: str = "", rule: str = BOILERPLATE) -> Violation:
    """A violation with rule boilerplate that mentions pests, so no tag may come from the rule."""
    return Violation(category=category, item=item, rule=rule, observation=observation)


@pytest.mark.parametrize(
    ("violation", "expected"),
    [
        pytest.param(
            v("Pest Control", "Removing Dead or Trapped Birds, Insects, Rodents and other Pest", "Observed pests."),
            ("pests_unspecified", "pest_control"),
            id="dead_trapped_pests",
        ),
        pytest.param(
            v("Pest Control", "Controlling Pests, Inspection/Harborage", "Observed inadequate procedures."),
            ("pest_control",),
            id="pest_paperwork_only",
        ),
        pytest.param(
            v("Storage", "Food Storage", "Observed boxes on floor. Pest Type: Rodent droppings"),
            ("rodents",),
            id="pest_type_field",
        ),
        pytest.param(
            v("S36 Insects, rodents, and animals not present", "6-501.111 Controlling Pests", "OBSERVED DEAD ROACHES."),
            ("roaches", "pest_control"),
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
        pytest.param(v("Records", "Temperature Logs"), (), id="temperature_logs_are_paperwork"),
        pytest.param(v("Handwashing", "Handwashing Sinks, Accessibility"), ("handwashing",), id="handwashing"),
        pytest.param(v("Availability", "Cleaning Agents and Sanitizers, Availability"), ("sanitizer",), id="sanitizer"),
        pytest.param(v("Operations", "Valid Permit"), ("permit",), id="permit"),
        pytest.param(v("Training Records", "Food Handler Cards"), ("training",), id="training"),
    ],
)
def test_tags_for(violation: Violation, expected: tuple[str, ...]) -> None:
    """Each rule fires on its evidence and nothing else."""
    assert tags_for(violation) == expected


@pytest.mark.parametrize(
    ("violation", "expected"),
    [
        pytest.param(
            v("Pest Control", PEST_ITEM, "Observed pests. Pest Type: German cockroaches"),
            ("roaches", "pest_control"),
            id="roaches_type",
        ),
        pytest.param(
            v("Pest Control", "Controlling Pests, Inspection/Harborage", "Observed mice droppings by the door."),
            ("rodents", "pest_control"),
            id="rodents_mice",
        ),
        pytest.param(
            v("Storage", "Food Storage", "Observed a dead rat under the shelf."),
            ("rodents",),
            id="rodents_rat",
        ),
        pytest.param(
            v("Pest Control", TREATMENT_ITEM, "Observed pests. Pest Type: rodent. Pest Condition: droppings observed."),
            ("rodents", "pest_control"),
            id="rodent_type_field",
        ),
        pytest.param(
            v(LEGACY_CATEGORY, "6-202.15 Outer Openings, Protected", "DOOR MUST BE SEALED SO NO RODENTS ENTER."),
            ("pest_control",),
            id="bare_rodents",
        ),
        pytest.param(
            v("Floors", "Cleaning", "Floors may provide harborage for insects, rodents, and other pests."),
            (),
            id="harborage_boilerplate",
        ),
        pytest.param(
            v(
                "Pest Control",
                "Controlling Pests, Inspection/Harborage",
                "Observed fruit flies and gnats by the drain.",
            ),
            ("flies", "pest_control"),
            id="flies_gnats",
        ),
        pytest.param(
            v("Pest Control", PEST_ITEM, "Observed pests. Pest Type: fly. Pest Condition: dead. needing fly lights."),
            ("flies", "pest_control"),
            id="fly_type_field",
        ),
        pytest.param(
            v("Ventilation", "Hood Systems", "Observed no fly light over the back door."),
            (),
            id="fly_light",
        ),
        pytest.param(
            v("Pest Control", TREATMENT_ITEM, "Observed pests. Location: Patio Pest Type: Ants"),
            ("other_pests", "pest_control"),
            id="other_ants",
        ),
        pytest.param(
            v("Pest Control", PEST_ITEM, "Observed pests. Pest Type: birds"),
            ("other_pests", "pest_control"),
            id="other_birds",
        ),
        pytest.param(
            v("Pest Control", TREATMENT_ITEM, "Observed pests. Pest Type: cockroach, rodent Pest Condition: living"),
            ("roaches", "rodents", "pest_control"),
            id="several_types",
        ),
        pytest.param(v("Pest Control", TREATMENT_ITEM, ""), ("pests_unspecified", "pest_control"), id="bamboo_empty"),
        pytest.param(
            v(LEGACY_CATEGORY, "6-501.111 Controlling Pests", "NO LICENSED PEST CONTROL SERVICE ON FILE."),
            ("pest_control",),
            id="legacy_control_only",
        ),
        pytest.param(
            v("Pest Control", "Controlling Pests, Inspection/Harborage", "Observed no pest control log."),
            ("pest_control",),
            id="paperwork_unspecified",
        ),
    ],
)
def test_pest_tags(violation: Violation, expected: tuple[str, ...]) -> None:
    """Pests are tagged by type; a pest-presence item with no readable type is pests_unspecified."""
    assert tags_for(violation) == expected


@pytest.mark.parametrize(
    ("violation", "expected"),
    [
        pytest.param(
            v("Pest Control", TREATMENT_ITEM, "Pest Type: Cockroach Pest Condition: Live"), "live", id="live_field"
        ),
        pytest.param(
            v("Pest Control", TREATMENT_ITEM, "Pest Type: Cockroach was present Pest Condition: living"),
            "live",
            id="live_living",
        ),
        pytest.param(
            v("Pest Control", PEST_ITEM, "Inspector killed a cockroach during the inspection."),
            "live",
            id="live_killed",
        ),
        pytest.param(
            v("Pest Control", PEST_ITEM, "Observed a roach on the prep table; PIC smashed it."),
            "live",
            id="live_smashed",
        ),
        pytest.param(
            v("Pest Control", PEST_ITEM, "Observed a cockroach crawling on the wall."),
            "live",
            id="live_crawling",
        ),
        pytest.param(
            v("Pest Control", PEST_ITEM, "Observed pests allowed to accumulate in traps. Pest Type: Cockroaches"),
            "dead",
            id="dead_traps",
        ),
        pytest.param(
            v("Pest Control", PEST_ITEM, "Observed a mouse on a glue board behind the cooler."),
            "dead",
            id="dead_glue",
        ),
        pytest.param(
            v("Pest Control", PEST_ITEM, "Pest Type: cockroach Pest Condition: Dead Number of Pests Present: 6"),
            "dead",
            id="dead_field",
        ),
        pytest.param(
            v("Pest Control", PEST_ITEM, "Pest Type: Rodent droppings Pest Condition: Unknown"),
            "droppings",
            id="droppings_rodent",
        ),
        pytest.param(
            v("Pest Control", TREATMENT_ITEM, "Observation: Multiple droppings found in the mop sink closet."),
            "droppings",
            id="droppings_unspecified",
        ),
        pytest.param(
            v("Pest Control", TREATMENT_ITEM, "Observed cockroach egg casings under the sink."),
            "droppings",
            id="droppings_eggs",
        ),
        pytest.param(v("Pest Control", TREATMENT_ITEM, ""), "not_stated", id="bamboo_empty"),
        pytest.param(
            v("Pest Control", PEST_ITEM, "Pest Type: cockroach Pest Condition: One living and 15 plus dead"),
            "live",
            id="live_beats_dead",
        ),
        pytest.param(
            v("Pest Control", PEST_ITEM, "Pest Type: cockroach, rodent Pest Condition: dead as well as mice droppings"),
            "dead",
            id="dead_beats_droppings",
        ),
        pytest.param(
            v(
                "Pest Control",
                TREATMENT_ITEM,
                "Observed cockroaches under the sink.",
                rule="Instructed PIC to remove any dead pests and live pests from the premises.",
            ),
            "not_stated",
            id="rule_ignored",
        ),
        pytest.param(
            v("Pest Control", PEST_ITEM, "Observed cockroaches by the sink. Instructed PIC to remove dead pests."),
            "not_stated",
            id="instruction_ignored",
        ),
        pytest.param(
            v("Surface Condition", "Nonfood-Contact Surfaces", "Damaged due to coffee dropping on the cabinet doors."),
            None,
            id="no_pest_tag",
        ),
        pytest.param(
            v(LEGACY_CATEGORY, "6-202.15 Outer Openings, Protected", "OBSERVED DOOR GAP; LIVE BAIT SHOP NEXT DOOR."),
            None,
            id="pest_control_only",
        ),
    ],
)
def test_pest_state(violation: Violation, expected: str | None) -> None:
    """Live beats dead beats droppings; nothing stated stays not_stated; no pest tag means no state."""
    assert tagged(violation).pest_state == expected


def test_tagged_fills_every_field() -> None:
    """tagged() sets tags, pest state and the labelled details together."""
    observation = "Observed pests allowed to accumulate in traps. Location: Back Storage Areas Pest Type: Cockroach"
    result = tagged(v("Pest Control", PEST_ITEM, observation))
    assert (result.tags, result.pest_state, result.details) == (
        ("roaches", "pest_control"),
        "dead",
        (("Location", "Back Storage Areas"), ("Pest Type", "Cockroach")),
    )


def test_inspector_fields_outrank_stock_wording() -> None:
    """'Allowed to accumulate in traps' is the form's stock phrase; the Pest Type field says droppings."""
    observation = (
        "Observed pests allowed to accumulate in traps. Location: Back storage room Pest Type: Rodent droppings "
        "Pest Condition: Number of Pests Present: 6 plus rodent droppings"
    )
    result = tagged(v("Pest Control", "Removing Dead or Trapped Birds, Insects, Rodents and other Pest", observation))
    assert (result.tags, result.pest_state) == (("rodents", "pest_control"), "droppings")
    living = "Observed pests. Pest Type: Cockroach Pest Condition: One living and 15 plus dead"
    assert tagged(v("Pest Control", "Removing Dead or Trapped", living)).pest_state == "live"
