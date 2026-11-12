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
    def first(self) -> str:
        """The earliest inspection date."""
        return min(i.date for i in self.inspections)


Rule = Callable[[Key, Key], Verdict | None]


def shared_permit_here(a: Key, b: Key) -> Verdict | None:
    """M1: the reports give both the same permit at the same address."""
    return SAME if a.permits & b.permits and a.address == b.address else None


RULES: tuple[Rule, ...] = (shared_permit_here,)


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


def _keys(inspections: tuple[Inspection, ...]) -> dict[str, Key]:
    by_slug: dict[str, list[Inspection]] = defaultdict(list)
    for inspection in inspections:
        by_slug[establishment_slug(inspection.name, inspection.address)].append(inspection)
    return {slug: Key(slug, tuple(found)) for slug, found in by_slug.items()}


def _pairs(slugs: Iterable[str]) -> set[tuple[str, str]]:
    ordered = sorted(slugs)
    return {(a, b) for n, a in enumerate(ordered) for b in ordered[n + 1 :]}


def candidates(keys: dict[str, Key]) -> list[tuple[str, str]]:
    """Pairs of keys worth comparing: they share a permit or an address."""
    shared: dict[tuple[str, str], set[str]] = defaultdict(set)
    for key in keys.values():
        shared["address", key.address].add(key.slug)
        for permit in key.permits:
            shared["permit", permit].add(key.slug)
    return sorted(set().union(*(_pairs(slugs) for slugs in shared.values())))


def _root(parent: dict[str, str], slug: str) -> str:
    while parent[slug] != slug:
        slug = parent[slug]
    return slug


def _group(keys: dict[str, Key], slugs: list[str]) -> Group:
    """Published under the earliest key's slug, so a place's page keeps its address when a new name joins it."""
    earliest = min(slugs, key=lambda s: (keys[s].first, s))
    return Group(earliest, tuple(i for s in slugs for i in keys[s].inspections), tuple(slugs))


def group(inspections: tuple[Inspection, ...]) -> list[Group]:
    """Inspections grouped by place: keys joined where match() says same, in the order each key first appears."""
    keys = _keys(inspections)
    parent = {slug: slug for slug in keys}
    for a, b in candidates(keys):
        if match(keys[a], keys[b]) == SAME:
            parent[_root(parent, a)] = _root(parent, b)
    members: dict[str, list[str]] = defaultdict(list)
    for slug in keys:
        members[_root(parent, slug)].append(slug)
    return [_group(keys, slugs) for slugs in members.values()]


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
