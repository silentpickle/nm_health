# Copyright (c) 2026 nm_health contributors
"""Labelled fields come out of the run-together observation text in order, without the leading sentence."""

import pytest

from nm_health.details import Details, detail, details_for

# Verbatim from the archived PDFs (pdftotext -layout), line breaks joined with a space as the parser does.
CHURCHS_701 = (  # 2026-09-20_2026-09-26_4526d9bed974.pdf, CHURCHS CHICKEN #701
    "Observed pests allowed to accumulate in traps. Location: Several location throughout facility Pest Type: Cockroaches"
    " Pest Condition: Dead Number of Pests Present: 30 plus"
)
ALBUQ_GRAND = (  # 2026-10-25_2026-10-31_0e0b9708501f.pdf, ALBUQ GRAND SENIOR APTS: an empty Pest Condition
    "Observed pests allowed to accumulate in traps. Location: Back storage room Pest Type: Rodent droppings"
    " Pest Condition: Number of Pests Present: 6 plus rodent droppings"
)
BURRITO_LADY = (  # 2025-11-02_2025-11-08_65a9dffb67d8.pdf, The Burrito Lady: free text, no labels
    "Observed rodent droppings in the back storage area next to refrigerators and boxes at the time of inspection."
    " PIC stated that they have pest control conducted every 6 months."
)


@pytest.mark.parametrize(
    ("observation", "expected"),
    [
        pytest.param(
            CHURCHS_701,
            (
                ("Location", "Several location throughout facility"),
                ("Pest Type", "Cockroaches"),
                ("Pest Condition", "Dead"),
                ("Number of Pests Present", "30 plus"),
            ),
            id="pest_fields",
        ),
        pytest.param(
            ALBUQ_GRAND,
            (
                ("Location", "Back storage room"),
                ("Pest Type", "Rodent droppings"),
                ("Number of Pests Present", "6 plus rodent droppings"),
            ),
            id="empty_dropped",
        ),
        pytest.param(BURRITO_LADY, (), id="no_labels"),
        pytest.param("", (), id="empty_observation"),
        pytest.param(
            "Observed food held above 41°F. Location: Prep make table Food Items and Temperature: Ham 54 °F",
            (("Location", "Prep make table"), ("Food Items and Temperature", "Ham 54 °F")),
            id="longest_label",
        ),
        pytest.param(
            "Observed sanitizer below parameters. Location: Meat packing area Concentration:100 ppm",
            (("Location", "Meat packing area"), ("Concentration", "100 ppm")),
            id="no_space",
        ),
        pytest.param(
            "Observed improper device. Location: Kitchen Type of Device: Snap trap Condition: does not contain rodents.",
            (("Location", "Kitchen"), ("Type of Device", "Snap trap"), ("Condition", "does not contain rodents")),
            id="trailing_period",
        ),
        pytest.param(
            "Observed boxes. location: kitchen floor",
            (),
            id="case_sensitive",
        ),
    ],
)
def test_details_for(observation: str, expected: Details) -> None:
    """Each label's value runs to the next label; the lead-in sentence and empty values are left out."""
    assert details_for(observation) == expected


def test_detail_joins_repeated_labels() -> None:
    """A label given twice yields both values; a missing label yields an empty string."""
    details = (("Location", "Kitchen"), ("Pest Type", "Cockroach"), ("Location", "Dry storage"))
    assert (detail(details, "Location"), detail(details, "Pest Condition")) == ("Kitchen; Dry storage", "")
