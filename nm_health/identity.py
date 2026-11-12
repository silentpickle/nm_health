# Copyright (c) 2026 nm_health contributors
"""Which inspections belong to the same place.

A place starts as a key: normalized name + normalized address (establishment_slug). Two keys are one place when the
records show it: the same permit at the same address (docs/place-identity.md). Names are never compared for
likeness, and the status feed never decides; its trade name only chooses which printed name a place is shown under.
"""

import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cached_property
from typing import Literal

from nm_health.ingest.normalizer import normalize_address, normalize_establishment_name
from nm_health.model import Inspection
from nm_health.signals import permit_of

NON_ALNUM = re.compile(r"[^a-z0-9]+")
DBA_RE = re.compile(r"\s+D\.?/?B\.?/?A\.?:?\s+", re.IGNORECASE)  # "Long Cao LLC DBA Dragon Sushi", "X d/b/a Y"
NOT_ALNUM_UPPER = re.compile(r"[^A-Z0-9]+")
CITY_SUFFIX_RE = re.compile(r",?\s+ALBUQUERQUE,?\s*NM\s*\d{5}(?:-\d{4})?\s*$", re.IGNORECASE)


def split_dba(name: str) -> tuple[str, str | None]:
    """(name people know, legal name or None): 'Long Cao LLC DBA Dragon Sushi' -> ('Dragon Sushi', 'Long Cao LLC')."""
    parts = DBA_RE.split(name.strip(), maxsplit=1)
    if len(parts) == 1 or not parts[1].strip():
        return name.strip(), None
    return parts[1].strip(), parts[0].strip()


def strip_city(address: str) -> str:
    """Drop a trailing 'ALBUQUERQUE, NM 87110' from a feed address."""
    return CITY_SUFFIX_RE.sub("", address.strip())


def establishment_slug(name: str, address: str) -> str:
    """Stable key for a place, e.g. 'acapulco-taco-840-san-mateo-blvd-se'.

    Same rule as the prototype store, so the CLI and the site agree. A renamed business is a new place.
    """
    name_part = NON_ALNUM.sub("-", normalize_establishment_name(name).lower()).strip("-")
    address_part = str(normalize_address(address)["slug"])
    return f"{name_part}-{address_part}"


def normalized_address(address: str) -> str:
    """Canonical street address ('1415 4TH ST SW, Unit H')."""
    return str(normalize_address(address)["normalized_address"])


def compact_name(name: str) -> str:
    """A name with case, spacing and punctuation gone: 'PAPA JOHN\u2019S PIZZA' and 'Papa Johns Pizza' agree."""
    return NOT_ALNUM_UPPER.sub("", normalize_establishment_name(name).upper())


# ---------- Matching two keys ----------

Verdict = Literal["same", "different", "cant_tell"]
SAME: Verdict = "same"
DIFFERENT: Verdict = "different"
CANT_TELL: Verdict = "cant_tell"


@dataclass(frozen=True)
class Key:
    """The inspections under one name + address slug."""

    slug: str
    inspections: tuple[Inspection, ...]

    @cached_property
    def address(self) -> str:
        """The normalized address every inspection here shares."""
        return normalized_address(self.inspections[0].address)

    @cached_property
    def permits(self) -> frozenset[str]:
        """Every permit these inspections name (signals.permit_of)."""
        return frozenset(p for i in self.inspections if (p := permit_of(i)) is not None)

    @cached_property
    def street(self) -> tuple[str, str]:
        """Street number and name, without quadrant or unit."""
        parts = normalize_address(self.inspections[0].address)
        return str(parts["street_number"]), str(parts["street_name"])

    @cached_property
    def reports(self) -> frozenset[str]:
        """The weekly reports that print these inspections."""
        return frozenset(i.report_file for i in self.inspections if i.report_file)

    @cached_property
    def first(self) -> str:
        """The earliest inspection date."""
        return min(i.date for i in self.inspections)


Rule = Callable[[Key, Key], Verdict | None]


def shared_permit_here(a: Key, b: Key) -> Verdict | None:
    """M1: the reports give both the same permit at the same address."""
    return SAME if a.permits & b.permits and a.address == b.address else None


def permit_elsewhere(a: Key, b: Key) -> Verdict | None:
    """M2: the same permit at another address: a misfiled summary row or a moved unit, so can't tell."""
    return CANT_TELL if a.permits & b.permits else None


def quadrant_typo(a: Key, b: Key) -> Verdict | None:
    """M3: one name, one street and number, the address differing only by quadrant or unit: can't tell."""
    same_name = compact_name(a.inspections[0].name) == compact_name(b.inspections[0].name)
    return CANT_TELL if same_name and a.street == b.street and a.address != b.address else None


def other_address(a: Key, b: Key) -> Verdict | None:
    """M4: different addresses are different places."""
    return DIFFERENT if a.address != b.address else None


def listed_together(a: Key, b: Key) -> Verdict | None:
    """M5: one weekly report lists both under their own names: the city counts two."""
    return DIFFERENT if a.reports & b.reports else None


def distinct_permits(a: Key, b: Key) -> Verdict | None:
    """M6: both name permits and none is shared: different businesses."""
    return DIFFERENT if a.permits and b.permits else None


def no_permit(_a: Key, _b: Key) -> Verdict | None:
    """M7: one address, two names, no permit on one side to compare: can't tell."""
    return CANT_TELL


RULES: tuple[Rule, ...] = (
    shared_permit_here,
    permit_elsewhere,
    quadrant_typo,
    other_address,
    listed_together,
    distinct_permits,
    no_permit,
)


def match(a: Key, b: Key) -> Verdict:
    """The first rule that decides; two keys no rule joins stay different places."""
    return next((verdict for rule in RULES if (verdict := rule(a, b)) is not None), DIFFERENT)


# ---------- Grouping ----------


@dataclass(frozen=True)
class Group:
    """The inspections of one place, under the slug its page is published at."""

    slug: str
    inspections: tuple[Inspection, ...]
    keys: tuple[str, ...] = ()  # the name + address slugs joined here
    maybe_same: tuple[str, ...] = ()  # slugs of other groups the records can't tell apart from this one


def _keys(inspections: tuple[Inspection, ...]) -> dict[str, Key]:
    by_slug: dict[str, list[Inspection]] = defaultdict(list)
    for inspection in inspections:
        by_slug[establishment_slug(inspection.name, inspection.address)].append(inspection)
    return {slug: Key(slug, tuple(found)) for slug, found in by_slug.items()}


def _pairs(slugs: Iterable[str]) -> set[tuple[str, str]]:
    ordered = sorted(slugs)
    return {(a, b) for n, a in enumerate(ordered) for b in ordered[n + 1 :]}


def candidates(keys: dict[str, Key]) -> list[tuple[str, str]]:
    """Pairs of keys worth comparing: they share a permit, an address, or a name on the same street and number."""
    shared: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for key in keys.values():
        shared["address", key.address].add(key.slug)
        shared["name", compact_name(key.inspections[0].name), *key.street].add(key.slug)
        for permit in key.permits:
            shared["permit", permit].add(key.slug)
    return sorted(set().union(*(_pairs(slugs) for slugs in shared.values())))


def _root(parent: dict[str, str], slug: str) -> str:
    while parent[slug] != slug:
        slug = parent[slug]
    return slug


def _published_slug(keys: dict[str, Key], slugs: list[str]) -> str:
    """The earliest key's slug, so a place's page keeps its address when a new name joins it."""
    return min(slugs, key=lambda s: (keys[s].first, s))


def _unclear(verdicts: dict[tuple[str, str], Verdict], parent: dict[str, str]) -> dict[str, set[str]]:
    """Roots each root can't be told apart from (pairs inside one joined group don't count)."""
    found: dict[str, set[str]] = defaultdict(set)
    for (a, b), verdict in verdicts.items():
        ra, rb = _root(parent, a), _root(parent, b)
        if verdict != CANT_TELL or ra == rb:
            continue
        found[ra].add(rb)
        found[rb].add(ra)
    return found


def group(inspections: tuple[Inspection, ...]) -> list[Group]:
    """Inspections grouped by place: keys joined where match() says same, in the order each key first appears.

    A pair match() can't tell apart stays two places, each naming the other in `maybe_same`.
    """
    keys = _keys(inspections)
    verdicts = {(a, b): match(keys[a], keys[b]) for a, b in candidates(keys)}
    parent = {slug: slug for slug in keys}
    for (a, b), verdict in verdicts.items():
        if verdict == SAME:
            parent[_root(parent, a)] = _root(parent, b)
    members: dict[str, list[str]] = defaultdict(list)
    for slug in keys:
        members[_root(parent, slug)].append(slug)
    published = {root: _published_slug(keys, slugs) for root, slugs in members.items()}
    unclear = _unclear(verdicts, parent)
    return [
        Group(
            published[root],
            tuple(i for s in slugs for i in keys[s].inspections),
            tuple(slugs),
            tuple(sorted(published[other] for other in unclear[root])),
        )
        for root, slugs in members.items()
    ]


# ---------- Names ----------


def shown_name(newest_first: tuple[Inspection, ...]) -> str:
    """The printed name the feed's trade name confirms, most recent first; else the most recent printed name."""
    confirmed = {compact_name(i.feed_name) for i in newest_first if i.feed_name}
    return next((i.name for i in newest_first if compact_name(i.name) in confirmed), newest_first[0].name)


def also_listed(newest_first: tuple[Inspection, ...], shown: str) -> tuple[Inspection, ...]:
    """The newest inspection printed under each other name (one that differs beyond case and punctuation)."""
    seen = {compact_name(shown)}
    found: list[Inspection] = []
    for inspection in newest_first:
        name = compact_name(inspection.name)
        if name in seen:
            continue
        seen.add(name)
        found.append(inspection)
    return tuple(found)
