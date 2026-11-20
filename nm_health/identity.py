# Copyright (c) 2026 nm_health contributors
"""Which inspections belong to the same place.

A place starts as a key: normalized name + normalized address (establishment_slug). Two keys are one place when the
records show it: the same permit at the same address (docs/place-identity.md). Names are never compared for
likeness, and the status feed never decides. A place is shown under its title as the latest report printed it.
"""

import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cached_property
from itertools import takewhile
from typing import Literal

from nm_health.ingest.normalizer import normalize_address, normalize_establishment_name
from nm_health.model import Inspection
from nm_health.signals import permit_of

NON_ALNUM = re.compile(r"[^a-z0-9]+")
DBA_RE = re.compile(r"\s+D\.?/?B\.?/?A\.?:?\s+", re.IGNORECASE)  # "Long Cao LLC DBA Dragon Sushi", "X d/b/a Y"
NOT_ALNUM_UPPER = re.compile(r"[^A-Z0-9]+")
CITY_SUFFIX_RE = re.compile(r",?\s+ALBUQUERQUE,?\s*NM\s*\d{5}(?:-\d{4})?\s*$", re.IGNORECASE)
ADDRESS_WORD = re.compile(r"[A-Z0-9]+")
QUADRANTS = frozenset({"NE", "NW", "SE", "SW"})
# Street types, dropped when comparing addresses: the Journal leaves them out, and a report may print one twice.
STREET_TYPES = frozenset(
    {
        "ST",
        "STREET",
        "AVE",
        "AVENUE",
        "BLVD",
        "BOULEVARD",
        "RD",
        "ROAD",
        "DR",
        "DRIVE",
        "LN",
        "LANE",
        "PL",
        "PLACE",
        "CT",
        "COURT",
        "PKWY",
        "PARKWAY",
        "HWY",
        "HIGHWAY",
        "WAY",
        "TRL",
        "TRAIL",
        "CIR",
        "CIRCLE",
        "LOOP",
        "SQ",
        "PLZ",
        "PLAZA",
        "TER",
        "TERRACE",
        "ALY",
    }
)
NAME_WORD = re.compile(r"[A-Z0-9]+")
STORE_NUMBER = re.compile(r"#\s*\d+")
APOSTROPHES = re.compile(r"['\u2019]")
# Words that don't tell two businesses at one address apart: company forms, "the", "and", and "restaurant" as spelled.
NAME_FILLER = frozenset(
    {
        "LLC",
        "INC",
        "CO",
        "CORP",
        "LTD",
        "LP",
        "PLLC",
        "THE",
        "AND",
        "RESTAURANT",
        "RESTAURANTS",
        "RESTARAUNT",
        "RESTURANT",
        "RESTAURAUNT",
    }
)


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


def street_words(address: str) -> tuple[str, str, str]:
    """Street number (digits), street name (its words, types dropped), quadrant: what makes one address.

    The Journal drops street types and units ("2100 Louisiana NE" for "2100 LOUISIANA BLVD NE", "2622 Central SE" for
    "2622 CENTRAL AVE SE, #A"); a report may print "2906A" for "2906", or a type and quadrant twice ("905 Yale Blvd SE
    BLVD SE"). Two names that share a number and street name but not a type are rare: one address, as a guess.
    """
    words = ADDRESS_WORD.findall(address.split(",", 1)[0].upper())
    if not words:
        return "", "", ""
    number = "".join(takewhile(str.isdigit, words[0]))
    rest = [word for word in words[1:] if word not in STREET_TYPES]
    quadrants = [word for word in rest if word in QUADRANTS]
    street = " ".join(word for word in rest if word not in QUADRANTS)
    return number, street, quadrants[-1] if quadrants else ""


def name_core(name: str) -> tuple[str, ...]:
    """A name's telling words: store numbers ("#31822", "824"), company forms, "the", "and", "restaurant" dropped.

    "TACO BELL #31822" and "Taco Bell", "BJ's Restaurant & Brewhouse" and "BJS RESTAURANT AND BREWHOUSE" agree.
    """
    text = APOSTROPHES.sub("", STORE_NUMBER.sub(" ", name.upper())).replace("&", " AND ")
    return tuple(word for word in NAME_WORD.findall(text) if not word.isdigit() and word not in NAME_FILLER)


def same_core(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """One name, spacing aside: "WAL MART" and "WALMART" agree."""
    return bool(a) and "".join(a) == "".join(b)


def begins(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """One name is the start of the other, word for word.

    "Walmart" and "Walmart Supercenter", "Blake's" and "Blake's Lotaburger"; not "Albertsons" and "AFC Sushi at
    Albertsons".
    """
    (short, _), (long_, words) = sorted((("".join(a), a), ("".join(b), b)), key=lambda found: len(found[0]))
    cuts = {sum(len(word) for word in words[: n + 1]) for n in range(len(words))}  # word ends in the longer name
    return bool(short) and short != long_ and long_.startswith(short) and len(short) in cuts


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

    @cached_property
    def journal_only(self) -> bool:
        """Only a newspaper's summary prints these inspections (nm_health.news_fold): no city report does."""
        return all(i.news is not None for i in self.inspections)

    @cached_property
    def address_words(self) -> tuple[str, str, str]:
        """Street number, street name and quadrant (street_words): how the Journal and the reports both print it."""
        return street_words(self.inspections[0].address)

    @cached_property
    def core(self) -> tuple[str, ...]:
        """The name's telling words (name_core)."""
        return name_core(self.inspections[0].name)


Rule = Callable[[Key, Key], Verdict | None]


def journal_place(a: Key, b: Key) -> Verdict | None:
    """M9: a key only the Journal prints, against any other key at one street number and street name.

    Same when the names agree (same_core) or one starts the other (begins), in one quadrant; one name in two
    quadrants can't be told apart (a likely quadrant typo); anything else stays apart. The guard in `group` (M10)
    keeps a name that starts several others from joining any.
    """
    if not (a.journal_only or b.journal_only):
        return None
    exact = same_core(a.core, b.core)
    if a.address_words[:2] != b.address_words[:2] or not (exact or begins(a.core, b.core)):
        return DIFFERENT
    if a.address_words[2] and b.address_words[2] and a.address_words[2] != b.address_words[2]:
        return CANT_TELL if exact else DIFFERENT
    return SAME


def shared_permit_here(a: Key, b: Key) -> Verdict | None:
    """M1: the reports give both the same permit at the same address."""
    return SAME if a.permits & b.permits and a.address == b.address else None


def feed_only(a: Key, b: Key) -> Verdict | None:
    """M8: a key no weekly report prints (the audit's feed-only records) joins only by a shared permit (M1)."""
    return DIFFERENT if not (a.reports and b.reports) else None


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
    journal_place,
    shared_permit_here,
    feed_only,
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
        shared["street", *key.address_words[:2]].add(key.slug)
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


def _join(parent: dict[str, str], pairs: Iterable[tuple[str, str]]) -> None:
    for a, b in pairs:
        parent[_root(parent, a)] = _root(parent, b)


def _touches_journal(pair: tuple[str, str], keys: dict[str, Key]) -> bool:
    return keys[pair[0]].journal_only or keys[pair[1]].journal_only


def _apart(p: str, q: str, verdicts: dict[tuple[str, str], Verdict], parent: dict[str, str]) -> bool:
    """Two keys not already one place, that no verdict joins."""
    if _root(parent, p) == _root(parent, q):
        return False
    return (verdicts.get((p, q)) or verdicts.get((q, p))) != SAME


def _torn(
    pairs: list[tuple[str, str]], verdicts: dict[tuple[str, str], Verdict], keys: dict[str, Key], parent: dict[str, str]
) -> set[str]:
    """Journal-only keys whose same pairs reach two keys that are apart: they'd join places the records keep apart."""
    partners: dict[str, set[str]] = defaultdict(set)
    for a, b in pairs:
        partners[a].add(b)
        partners[b].add(a)
    return {
        key
        for key, found in partners.items()
        if keys[key].journal_only and any(_apart(p, q, verdicts, parent) for p, q in _pairs(found))
    }


def _join_journal(
    verdicts: dict[tuple[str, str], Verdict], keys: dict[str, Key], parent: dict[str, str], *, exact: bool
) -> dict[tuple[str, str], Verdict]:
    """M10: join the Journal's same pairs of one kind, except where a key would bridge places kept apart.

    One kind is exact names, the other one name starting another. A key whose pairs would join places kept apart
    joins none of them: those pairs become can't tell. Returns the verdicts with that applied.
    """
    pairs = [
        pair
        for pair, verdict in verdicts.items()
        if verdict == SAME
        and _touches_journal(pair, keys)
        and same_core(keys[pair[0]].core, keys[pair[1]].core) == exact
    ]
    torn = _torn(pairs, verdicts, keys, parent)
    _join(parent, [pair for pair in pairs if not torn & set(pair)])
    return {pair: CANT_TELL if pair in pairs and torn & set(pair) else verdict for pair, verdict in verdicts.items()}


def group(inspections: tuple[Inspection, ...]) -> list[Group]:
    """Inspections grouped by place: keys joined where match() says same, in the order each key first appears.

    City keys join first; then Journal-only keys with the same name, then those whose name starts another's, each
    only where it can't bridge two places kept apart (M10). A pair match() can't tell apart stays two places, each
    naming the other in `maybe_same`.
    """
    keys = _keys(inspections)
    verdicts = {(a, b): match(keys[a], keys[b]) for a, b in candidates(keys)}
    parent = {slug: slug for slug in keys}
    _join(parent, [pair for pair, v in verdicts.items() if v == SAME and not _touches_journal(pair, keys)])
    verdicts = _join_journal(verdicts, keys, parent, exact=True)
    verdicts = _join_journal(verdicts, keys, parent, exact=False)
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


def _printed(newest_first: tuple[Inspection, ...]) -> tuple[Inspection, ...]:
    """The inspections a weekly report prints; all of them when none is (the audit's feed-only places)."""
    return tuple(i for i in newest_first if i.has_details) or newest_first


def title(newest_first: tuple[Inspection, ...]) -> Inspection:
    """The inspection whose printed title (name, address) the place is shown under: the latest a report prints."""
    return _printed(newest_first)[0]


def also_printed(newest_first: tuple[Inspection, ...], shown: str) -> tuple[Inspection, ...]:
    """The newest inspection printed under each other name (one that differs beyond case and punctuation)."""
    seen = {compact_name(shown)}
    found: list[Inspection] = []
    for inspection in _printed(newest_first):
        name = compact_name(inspection.name)
        if name in seen:
            continue
        seen.add(name)
        found.append(inspection)
    return tuple(found)


def journal_printed(newest_first: tuple[Inspection, ...], shown: str) -> tuple[Inspection, ...]:
    """The newest Journal-sourced inspection under each name that differs from the one shown (M9's guesses, shown)."""
    seen = {compact_name(shown)}
    found: list[Inspection] = []
    for inspection in (i for i in newest_first if i.news is not None):
        name = compact_name(inspection.name)
        if name in seen:
            continue
        seen.add(name)
        found.append(inspection)
    return tuple(found)
