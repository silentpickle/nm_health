# Place identity: when are two records the same place?

Written 2026-11-12. The trigger: the Nov 1–7, 2026 report prints El Branco Restaurant's 11/03 re-inspection
(RT-FOODEST-102994-2026, Approved) under the name "Maria Cabrera". The site keys places by name and address, so it
shows "Maria Cabrera" as a new place, and El Branco's 10/30 Unsatisfactory looks unresolved.

**In short**

- Today a place is just *normalized name + normalized address*. Permit numbers play no part in grouping.
- Across the whole archive, the same name-drift split happens **once**: El Branco. A second "same permit, two
  places" case turns out to be a **parser bug**. Two summary headers with a curly apostrophe (’) are not recognized,
  so those inspections are filed under the previous business's name. That is a separate fix.
- The real cause is that the reports sometimes print the **legal or owner name** instead of the trade name. In 8 of
  the 313 report inspections the feed also lists, the report's name is the feed's legal name, not its DBA. El Branco
  is the only one where both names show up for the same permit, so far. It will recur.
- Recommended fix: classify each candidate pair of place keys as **same place / different place / CAN'T TELL**,
  using permit numbers first. Merge only "same". Keep "CAN'T TELL" apart, with a visible flag and a way to settle
  it later. On the real data: 2 merges, 4 CAN'T TELL (all from the old no-permit reports, none inside the site's
  12-month window).

Every number below comes from a script in
`/private/tmp/claude-502/-Users-davidcrandall-test-qwen-nm-health--claude-worktrees-time-unit-options-consistency-84c561/3507d124-bd11-4b28-843e-ff37128c669c/scratchpad/identity/`
(called `identity/` below), run with `uv run python identity/<script>.py <pickle>`. The input is the full rebuild in
`.../scratchpad/resolution/rebuilt.pkl`: all 14 archived PDFs plus the whole feed, made with
`rebuild(settings, None, feed_details=True)`. Each script's output is saved beside it as `<script>.out`. A
`.window.out` file is the same script run on `identity/rebuilt_window.pkl`, which keeps only inspections on or after
2025-11-12, the window `nm-health site` uses (`identity/window.py`). Line numbers refer to commit `63790bc`.

---

## 1. How identity works today

### From inspection to place

| Step | Where | What it does |
|---|---|---|
| Parse | `rebuild.py:85` `_from_current`, `legacy_parser.py:97` `_synthetic_id` | One `Inspection` per row: name and address as printed, `permit_number` from the summary table's permit line (current layout only) |
| DBA split | `rebuild.py:143` `_prepare` → `identity.py:13` `split_dba` | "Long Cao LLC DBA Dragon Sushi" becomes name "Dragon Sushi", legal name "Long Cao LLC". Applies only when the report prints "DBA" |
| Dedupe | `rebuild.py:219` | Inspections are keyed by (inspection ID, date). A later report wins |
| Feed merge | `rebuild.py:183` `merge_feed` | The feed adds **only coordinates**, matched by (ID, date) or else by normalized address. Feed names never reach the site |
| What the site may state | `viewmodel.py:483` `stated` | Report inspections dated inside their report's week |
| **Grouping** | `viewmodel.py:352` `group_places` | `by_slug[establishment_slug(name, address)]` |
| The key | `identity.py:26` `establishment_slug` | `normalize_establishment_name` (upper case, trailing punctuation stripped; `ingest/normalizer.py:44`) + `normalize_address(...)["slug"]` (street types, quadrant, unit; `normalizer.py:52`). Every run of non-alphanumerics becomes `-`. Its docstring: "A renamed business is a new place." |
| Display name | `viewmodel.py:340` `build_place` | `name = latest.name`, the **most recent** inspection's name |
| URL | `site.py:132`, `site_html.py:273` `place_href` | `place/<slug>.html` |
| Other users of the slug | `database.py:57` (CLI DB), `judge.py:151` (`data/judgements.json` keyed by slug), `audit.py:393` and `spotcheck.py:307` (both call `group_places`) | |

### Permits and status today

`signals.py:136` `permit_of` gives an inspection's permit: an old-style ID that *is* the permit (`PT\d+`), else the
summary table's permit line. `signals.py:154` `standing` keeps each permit's latest result *within a place*. This is
commit `9dddd45`, "Status today per permit". `viewmodel.py:523` `permit_lines` quotes the city's
"Operational Status" line for each permit. Permits are used **inside** a place, never to decide **which** place.

### The feed's names

`feed.py:146` `_names`: the feed carries a company column (`ticket_detail_entry2`) and a DBA column
(`ticket_detail_entry13`). With a DBA, the DBA is the name and the company becomes `legal_name`. `identity.py:21`
`strip_city` drops ", ALBUQUERQUE, NM 87xxx" from feed addresses. None of this affects grouping on the site, because
feed-only inspections are not stated. The audit, however, groups feed-only inspections under their feed names (see §2.4).

### IDs and permits by layout (`identity/overview.py`)

| Layout | Inspection ID shapes | Permit available? | Inspections the site states (whole archive) |
|---|---|---|---|
| Current (Oct 2025 on) | `PT0155329` (old-style: ID = permit), `RT-FOODEST-102994-2026`, `CAC-Food-…`, `COM-FOODES-…`, `RT-RET-…`, `RT-MBFOOD-…`, `RT-PRC-…` | Yes, from the summary permit line. Permit shapes: `PT0000000`, `FOODEST-2025-012746`, `FOODEST-2025-00423`, `MOBILE-2025-014128` | 425 of 425 have a permit |
| Legacy "Activity Date" (2021–Jan 2025) | Synthetic `legacy-<date>-<name>-<address>` | **No** | 170 of 170 have none |
| Transitional (one file, `unknown-week_2025-03-10_…`) | none | none | Parses to **0** inspections (side note: its 56 headers read "Food Establishment Class C - NAME", `identity/headers.py`) |

**Without a permit:** 170 of 595 stated inspections (28.6%), all of them legacy. Inside the site's 12-month window it
is 0 of 346 (`overview.window.out`). The new-style re-inspection IDs (`CAC-Food-…`, `RT-FOODEST-…`) do get a permit
from the summary table, every time. So `docs/assumptions.md`'s line "an inspection with no permit number (most
re-inspections since late 2025)" no longer matches the parsed data.

---

## 2. How big the problem is

Whole archive: 595 stated inspections, 412 place keys, 326 permits. Site window: 346 inspections, 226 place keys, 265
permits.

### 2.1 Same permit under 2+ place keys (`identity/permit_split.py`)

**2 permits**, the same 2 in the whole archive and in the window:

| Permit | Place keys | Dates and results | What it is |
|---|---|---|---|
| FOODEST-2025-012746 | "El Branco Restaurant", 100 Coors Ave SW / "Maria Cabrera", same address | 10/30/2026 Unsatisfactory / 11/03/2026 Approved | **Owner name printed as the establishment name.** For the 11/03 inspection, the feed's DBA is El Branco Restaurant and its company is Maria Cabrera |
| PT0155329 | "Fuel Ignited by Sparks LLC", 9250 Golf Course Rd NW B / "PAPA JOHNS PIZZA", 9500 Montgomery Blvd NE 11 | 12/24/2025 Approved / 12/29/2025 Approved | **Parser bug.** The PDF's summary header reads "PAPA JOHN’S PIZZA" with a curly apostrophe. The header regex (`ingest/parser.py:250`, `est_re`) rejects it, so the 12/24 row is filed under the business listed above it |

The parser bug also hits one other header (`identity/headers.py`: 2 header misses in current-layout reports, both
caused by ’). "LET’S EAT THAI CUISINE LLC"'s 11/04/2025 inspection (PT0157002) is filed under **Jimmy John's**. That
gives Jimmy John's a second permit it doesn't hold, and Let's Eat Thai has no page. Both rows are outside today's
window, so the live site isn't affected. The bug isn't about identity and gets its own fix commit (§4).

### 2.2 Same address, 2+ names (`identity/address_names.py`)

Whole archive: **15 addresses** carry 32 place keys. Window: **7 addresses**, 14 keys.

| Class | Whole archive | Window | Examples | Reading |
|---|---|---|---|---|
| A. Shared permit | 1 | 1 | El Branco / Maria Cabrera | Same business, name drift |
| B. One side has no permit (legacy), names alike | 6 | 0 | "Taco Bell" (Jan 2025) / "TACO BELL 2926" (Oct 2026); "Taylor Ranch Community Center" / "COA - Taylor Ranch Community Center"; "BUBBAS 33" (2021) / "BUBBAS HOLDINGS LLC" (2026); Sheraton "– Bar" / "– Kitchen"; two Job Corps names; two academies at 4100 New Vistas | Mixed. Some are drift. Others (Sheraton bar vs kitchen, same week) are separate operations, so "names alike" can't decide it |
| C. No permit, names differ | 2 | 0 | Costco / Canteen / Club Demonstration Services (same day); hospital cafeteria / shelter kitchen | Separate operations listed side by side |
| D. Different permits, names alike | 0 | 1 | Two vendors at 5701 Gibson SE ("…FOOD LLC") | Separate businesses. The similarity is only the word "food" |
| E. Different permits, inspected in the same period | 3 | 1 | Starbucks / Firehouse Subs (1720 Unser NW); Duke City BBQ / Boxing Bear | Co-located businesses |
| F. Different permits, seen one after the other | 3 | 4 | Twisters / Wingstop (425 Eubank NE); BJ's / Winrock Stadium 16; Fuddruckers / Hot Dog on a Stick | Mostly malls and strip centres sharing a street number, not succession |

Two lessons: **different permits mean different businesses** in every case, and **name similarity is not evidence**,
in either direction.

### 2.3 One place key with 2+ permits (`identity/address_names.py`, second section)

**41 of 412 keys** (whole archive), **34 of 226** (window). In 40 of the 41 (33 of 34), two or more of the permits were
inspected on the same day: Albertsons #911 (3 retail permits), Tiny Grocer (4), Costco, Target, Walmart, Allsup's,
Quick Track, breweries with a processor permit, restaurants with a bar permit. These are multi-permit sites, which
`9dddd45` handles. Two keys are on the list only because of the parser bug: Jimmy John's (whole archive only) and Fuel
Ignited (both runs; its 2 permits on different days is the one exception). **No genuine wrong merge** shows up under
the current key.

Same name at 2+ addresses: 15 names, almost all chains. One pair shares a street number: "GOOD FELLAS PIZZERIA" at
5844 Osuna Rd **NW** (legacy, 2021) and **NE** (2026), probably a quadrant typo.

### 2.4 Report name vs feed name (`identity/feed_names.py`)

313 of 595 stated inspections are matched in the feed by (ID, date). The legacy synthetic IDs can't match. 301 carry
the same normalized name; **12 differ**:

| Kind | Count | Cases (report name → feed DBA) |
|---|---|---|
| Report prints the **feed's legal/company name** | 8 | Maria Cabrera → El Branco Restaurant; Cottonwood 3703 LLC → Dave's Hot Chicken; Fuel Ignited by Sparks LLC → Chicago Pizza Kitchen; Asian Food Handmade Tea Garden LLC → Sushi Dumpling Tea; MOM AND POP PIZZA SHOP → RICHIE BS PIZZA; Duke City BBQ 3 LLC → Duke City BBQ (×2); PHAT STAX BURGERS → PHAT STAX BURGERS EASTSIDE |
| Parser bug (§2.1) | 2 | Jimmy Johns ← Let's Eat Thai; Fuel Ignited ← Papa John's |
| Spelling or suffix | 2 | "Crepe Brule" / "Crepe Brulee"; "Dunkin Donuts - Wyoming, LLC" / "Dunkin Donuts" |

So the site already shows several places under a company name people wouldn't search for, such as Dave's Hot
Chicken under "Cottonwood 3703 LLC". It splits only when a later report flips to the other name for the same permit.

**Phat Stax** is the next likely split. The reports print "PHAT STAX BURGERS" (11/03 Closure, 11/05 Unsatisfactory,
permit FOODEST-2026-000467). The feed's DBA is "…EASTSIDE" and shows an Approved on 11/10 that no report on file
covers yet. If the Nov 8–14 report prints the EASTSIDE name, the site splits it exactly like El Branco. The audit
already does: grouping report and feed-only inspections together within the window, **2** report-backed keys sit
beside a feed-only key under the feed's DBA name (Fuel Ignited / Chicago Pizza Kitchen, Phat Stax / …EASTSIDE)
(`identity/audit_split.py`).

Feed-wide drift couldn't be measured: no `PT…` ID appears twice in the feed (`feed_names.out`, last section), so the
feed can't show one permit under two names.

### 2.5 What a split or a wrong merge does on the site

| Failure | Status today | Lists and filters | Strip and history | Closures and `reopened_flag` | Map |
|---|---|---|---|---|---|
| **Split** (El Branco) | The old key keeps its last result for good: El Branco shows **Unsatisfactory** in red. The new key starts clean | El Branco counts among red places; the new name looks like a new business | History is cut in two, each half under a different name | A closure on the old key never ends: `closure_in_force` stays True, the place sits in the "closed" filter, and `reopened_flag` never fires | Two dots on the same coordinates |
| **Wrong merge** (parser bug, or a careless permit rule) | `standing` lists another business's permit as if it were this one's ("1 of 2 permits closed") | Wrong flags | Another business's inspections and pest citations appear on this page | Another business's closure can "reopen" this one | One dot instead of two |

El Branco before and after a merge (`identity/el_branco.py`):

| | Before (split) | After (merged) |
|---|---|---|
| El Branco row | Unsatisfactory chip (red), no flag | Approved chip, flag "Closure or unsatisfactory Oct 30" |
| "Maria Cabrera" row | Approved, a separate place | gone (one place) |
| What-if: had 10/30 been a **Closure** | `closure_in_force` = True for good, no reopened flag | `reopened_flag` = **"Closed 4 days, reopened Nov 3"** (both weeks are on file) |
| Display name | — | "Maria Cabrera" under today's rule (`name = latest.name`). **The name rule must change too** (§3.3) |

---

## 3. Options

### 3.1 How to key a place

| Option | For | Against |
|---|---|---|
| **Keep name + address** (today) | Simple; stable URLs | Splits El Branco now and Phat Stax probably next week; every legal/DBA flip splits |
| **Permit as the key** | The city's own identity | 28.6% of the archive has no permit; one site has many permits (41 keys); a misfiled summary row would join two businesses (the PT0155329 bug did exactly that) |
| **Name + address, joined by evidence** (recommended) | Keeps today's keys and URLs; merges only on proof; works with no permit | Needs a matcher and a third state for doubtful pairs |
| **Alias table only** | Fully human-controlled | Someone has to notice every split. El Branco would show wrong until then |

A match is never a plain yes/no. Some pairs can't be decided from the records: a legacy "Taco Bell" and "TACO BELL
2926" at the same address 21 months apart, with no permit on one side. The project already has a word for that. The
spot-check asks for SUPPORTED / CONTRADICTED / **CAN'T TELL** (`spotcheck.py:60`), and the judge answers
yes / no / **unsure** and operating / closed / **unknown** (`judge.py:25`). Identity should use the same three ways:
**same place / different place / CAN'T TELL**.

### 3.2 What counts as evidence (measured on the 21 candidate pairs, `identity/classify.py`)

Candidate pairs are keys that share a permit, an address, or a name and street number. There are 21 in the whole
archive and 8 in the window. The matcher in `classify.py` applies the first rule that fits:

| # | Rule | Verdict | Whole archive | Window |
|---|---|---|---|---|
| 1 | Shared permit, same address | same | 2 (El Branco; Papa John’s/Johns once the parser bug is fixed) | 2 |
| 2 | Shared permit, different address | CAN'T TELL (a misfiled row or a moved mobile unit) | 0 after the parser fix (1 before: PT0155329) | 0 |
| 3 | Different address; same name and street, differing only by quadrant or unit | CAN'T TELL | 1 (Good Fellas NE/NW) | 0 |
| 4 | Different address otherwise | different | — | — |
| 5 | Listed side by side in one report | different (the city listed them as two) | 11 | 4 |
| 6 | Both have permits, none shared | different | 4 | 2 |
| 7 | Same address, no permit to compare | CAN'T TELL | 3 (Taco Bell, Taylor Ranch, Bubba's) | 0 |
| | **Total** | 2 same · 15 different · **4 CAN'T TELL** | | 2 same · 6 different · **0 CAN'T TELL** |

A tried rule, "the feed names one key's name as the other's legal name or DBA, so same", decided **no** pair the
permit rule hadn't already decided. It isn't needed for grouping, which keeps the feed out of identity, in line with
"the feed only places map dots".

### 3.3 Which name to show

The names in a merged group are all printed by the reports, so any of them can be quoted. The choice only decides
which one leads.

| Rule | El Branco gets | Problem |
|---|---|---|
| Most recent (today) | Maria Cabrera | Shows the owner's name |
| Most frequent | tie 1–1 | Ties are common for new places |
| Earliest | El Branco | A real rename on the same permit keeps the old name |
| Feed's DBA | El Branco | The feed would be making a statement, which the rules forbid… |
| **Feed's DBA only to choose among names the reports printed**, else most frequent, ties to the most recent | **El Branco** | Uses the feed to pick, never to supply a word. Owner's call (§5) |

Display: **"El Branco Restaurant"**, with a line under the address: *"Also listed in the city's reports as: Maria
Cabrera (Nov 3, 2026)"*, linked to that report page. Every name printed stays visible and sourced.

### 3.4 Interaction with "Status today per permit" (`9dddd45`)

`standing` works on whatever inspections a place holds. A **same** merge only ever joins keys that share a permit, so
the merged inspections compete per permit as before: El Branco's 11/03 Approved supersedes its 10/30 Unsatisfactory.
A merge of keys with **disjoint** permits would make `standing` list two businesses' permits as one place's. That is
why rule 6 says "different" and why no rule merges on name similarity. `permit_lines` reads the latest report that
lists the place, which after the merge is Nov 1–7, so it correctly quotes "Operational Status – Open".

### 3.5 URLs

Today the URL is `place/<slug>.html`, and the slug follows whichever name is on the key. Options:

- **Group slug = the earliest key's slug** (El Branco keeps `el-branco-restaurant-100-coors-ave-sw`). Every other
  key in the group gets a redirect page at its own old URL: a tiny HTML with `meta refresh`, `rel=canonical` and a
  plain link, regenerated on every build because `write_site` wipes `site/`. Any link already shared to
  `maria-cabrera-….html` keeps working.
- Slug from the display name: it changes whenever the chosen name changes. Not recommended.
- A slug can still disappear when its inspections age out of the 365-day window, as any place's can today.

`data/judgements.json` (20 entries, keyed by slug) and the CLI DB (`database.py:57`) should use the group slug. None
of the 20 judged slugs is in a merged group or a CAN'T TELL pair today.

---

## 4. The design (owner's answers of 2026-11-12 applied)

### What gets built

1. **`identity.match(a, b) -> Verdict`**: `"same" | "different" | "cant_tell"`, using the rules table in §3.2. Each
   rule is one small function, and a list runs them in order; the first decisive answer wins. Names are never
   compared for similarity.
2. **`identity.group(inspections)`**: starts from today's name + address keys and finds candidate pairs (keys that
   share a permit, an address, or a name and street number). It joins only the **same** pairs and records each
   **CAN'T TELL** pair on both sides. `viewmodel.group_places` builds places from these groups, and the site, audit,
   spot-check and judge all go through it.
3. **The shown name**: of the names the reports printed for the group, the one the feed's trade (DBA) name confirms
   for any of the group's inspections. The feed only chooses; it never supplies a word. With no confirmation, the
   name printed on the most inspections wins, and a tie goes to the most recent. Under the shown name, the place
   page says *"Also listed in the city's reports as: Maria Cabrera"*. To make this possible, each inspection keeps
   the feed's DBA for the same (ID, date) as `feed_name`. It is used for nothing else.
4. **The URL** stays the slug of the group's earliest key, so El Branco keeps
   `el-branco-restaurant-100-coors-ave-sw`. The other keys' URLs stop being written. **Redirects are deferred**
   (§5).
5. **Review marker: "merged by permit, names differ."** The owner's ruling: merge, "but definitely mark it in such a
   way we come back and really deal with it". This applies to a **same** merge whose names still differ once
   punctuation and spacing are removed. ("PAPA JOHN’S" against "PAPA JOHNS" is not a difference.) Such a place
   carries a durable, low-key marker:
   - **Place page**: a quiet note, *"Merged by permit; names differ."*, next to the "Also listed as" line.
   - **`places.json`**: flag bit `FLAG_MERGED_BY_PERMIT = 16`, mirrored in `shared.js` as `mergedByPermit`.
   - **Audit**: a `place_identity` check that lists every such merge (permit, names, dates), alongside every
     CAN'T TELL pair.
   - **Spot-check packet**: a review statement for each sampled place that carries the marker. For example: "The
     site treats El Branco Restaurant and Maria Cabrera at 100 Coors Ave SW as one place because the reports give
     both the same permit."
6. **CAN'T TELL**: the records stay apart, and nothing is guessed.
   - Row flag (`_row_flags`): *"May be the same business as Taco Bell"*. The place page links the other place.
   - `places.json`: flag bit `FLAG_MAYBE_SAME = 8`, mirrored in `shared.js` as `maybeSame`.
   - Spot-check: the statement *"<X> and <Y> at <address> may be the same business; the site keeps them apart"*,
     answered SUPPORTED / CONTRADICTED / CAN'T TELL like every other statement.
   - Audit: listed by `place_identity`.
   - Settling one later (deferred): an alias entry written by a person, or a yes / no / unsure judge question.
     Neither is built yet, and the marker and flag don't need either one.

### Edge cases

| Case | Expected |
|---|---|
| Same permit, same address, unrelated names (El Branco / Maria Cabrera) | same; shown as El Branco when the feed confirms it; "also listed as" line; review marker |
| Same permit, same address, apostrophe or spacing only (PAPA JOHN’S / PAPA JOHNS) | same; no review marker |
| Same permit, different address (a misfiled row, as PT0155329 was before the parser fix) | CAN'T TELL, never merged |
| One key, several permits (Albertsons, Quick Track 93's swapped rows) | one key, as today; `standing` unchanged |
| Same address, disjoint permits (Twisters / Wingstop) | different, no flag |
| Listed side by side in one report (Sheraton bar / kitchen) | different |
| Old no-permit key and current key at one address (Taco Bell / TACO BELL 2926) | CAN'T TELL |
| Quadrant typo (Good Fellas NE / NW) | CAN'T TELL |
| A key ages out of the window | the group's URL can change, as any place's can today |
| Feed-only inspections (audit only) | no permit, so they join only through rules 5 and 7; feed names never merge |

### Commits and tests

1. Docs: this file, and a correction to `docs/assumptions.md`'s line about re-inspections with no permit number.
2. **Pin**: `tests/test_identity.py` compares places.json, the All time page and every place page against a golden,
   over a fixture with one pair of records per case above.
3. **Fix: the parser reads a curly apostrophe in a summary header**, with its own test.
4. **Refactor**: grouping moves into `identity.group`; the golden is unchanged and still green.
5. **Fix: one place per permit at one address**: the shown name, the "also listed" line and the review marker. The
   golden changes only for the merged pairs.
6. **CAN'T TELL**: `FLAG_MAYBE_SAME`, the row flag, the spot-check statement and the audit check.

---

## 5. Owner's answers, and what stays open

1. **Shown name**: yes, the feed's DBA chooses among the names the reports printed, with an "Also listed in the
   city's reports as" line. Built.
2. **Same permit, same address, unrelated names**: merge automatically, and mark the merge so it gets dealt with
   properly (the review marker in §4.5). Built.
3. **Open design question: a trade name and a legal/business name for every place.** The owner is still deciding;
   nothing is built. If two fields are adopted, my view is:
   - *Trade name*: the name people know. It comes from the report where the report prints "DBA". Otherwise it is
     the report-printed name the feed's DBA confirms. Failing both, it is the feed's DBA itself, which would be the
     feed's first statement on the site, so it would need its own label ("listed in the city's status feed as").
   - *Legal/business name*: the report's pre-"DBA" part, or the feed's company column.
   - *Shown*: the trade name as the heading, with the legal name on a smaller line, as `legal_name` is today.
   - *Search*: both names, plus every name the reports printed. This would fix the 8 places where the site shows a
     company name (for example "Cottonwood 3703 LLC" for Dave's Hot Chicken).
4. **Redirects for old place URLs**: deferred until #3 is decided.
5. **The 4 CAN'T TELL pairs from the old no-permit reports**: deferred. They stay flagged, with no alias entries.
   All four are outside the 12-month window today.
