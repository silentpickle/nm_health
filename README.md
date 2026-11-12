# ABQ Food Inspection History

The City of Albuquerque publishes restaurant inspections as **one PDF that it overwrites every week**
(`chpd_main_inspection_report.pdf`). Once a week rolls off, its closures, roach citations and red tags are gone.
This project keeps every copy and turns them into a history per restaurant:

> **Little Bear Coffee**, 330 Tijeras St NW: *Last pest citation Sep 24, 2026 · inspected 1 time since, most recently Sep 25, 2026.*

It only claims what the archive shows. A place with no pest citations reads "No pest citations in N archived
inspections (first – last)", never "pest-free": inspections happen a few times a year, and weeks nobody saved
are missing.

## How it works

```
cabq.gov PDF ──daily──▶ data/archive/<week>_<sha>.pdf ──▶ parse (3 layouts) ──▶ tag ──▶ site/  (GitHub Pages)
                         + manifest.jsonl (committed)                                └──▶ data/nm_health.db (CLI)
```

1. **Archive** (`collect.yml`, daily 15:00 UTC): download the PDF, refuse anything that isn't a PDF, and save it
   if those bytes are new. Archiving never parses, so a PDF the parser can't read yet is still kept. Amended
   re-issues are kept beside the original.
2. **Rebuild**: parse every archived PDF, oldest week first. The later report wins when two state the same
   inspection (keyed by inspection ID + date: routine inspections reuse the permit number as their ID).
3. **Tag** each violation from the inspector's observation, not the rule boilerplate: roaches, rodents, flies,
   other pests, each marked live / dead / droppings / not stated (the inspector's Pest Type and Pest Condition
   fields first). Door gaps and pest paperwork are "pest_control". The status feed adds coordinates, counts and
   every inspection whose weekly report wasn't saved (status only).
4. **Publish** (`site.yml`): plain HTML pages that read without JavaScript (This week, Last month and All time under
   the Inspections tab, Places, Map, About, one page per place), a slim `places.json` that `places.js` (search, filters) and `map.js` (packages/citymap) read.
   The site states only what a weekly report on file says, and links every statement to that report's page (a
   byte-for-byte copy under `reports/`); the status feed only places map dots. See `docs/assumptions.md`.

Three report layouts are parsed: the current one (late 2025 on), the early-2025 transitional one, and the
2021–2024 "Activity Date" one. The last two have no inspection or permit numbers, so their IDs are synthetic.

## Use it

Needs `uv`, `node` (site JS checks only) and poppler (`brew install poppler`).

```bash
uv sync && npm ci && uv run pre-commit install
```

```bash
uv run nm-health archive              # save this week's PDF if it's new
uv run nm-health backfill-wayback     # recover older weeks from the Internet Archive
uv run nm-health ingest               # rebuild data/nm_health.db from the archive
uv run nm-health site                 # render site/ (open site/index.html)
uv run nm-health audit                # check our assumptions against the PDFs and feed (docs/assumptions.md)
uv run nm-health spotcheck | pbcopy   # a packet to paste into any LLM: site statements + city records
uv run nm-health judge                # local, needs agy: second opinion on long closures (data/judgements.json)
uv run nm-health search "pho"         # CLI lookups against the database
uv run nm-health lookup "Little Bear Coffee"
```

`uv run nm-health serve` still starts the prototype's local dashboard on the database.

## Layout

| Path | What |
|---|---|
| `config.toml` | Every setting (source URL, paths, Wayback endpoints). No secrets; none are needed. |
| `data/archive/` | The archive: every distinct PDF + `manifest.jsonl`. The only data that is committed. |
| `nm_health/archive.py`, `wayback.py` | Download / backfill and dedupe. |
| `nm_health/ingest/parser.py` | Current layout (the prototype's parser, pinned by `tests/golden/`). |
| `nm_health/legacy_parser.py` | 2021–2024 and early-2025 layouts. |
| `nm_health/tags.py` | One small rule per tag. |
| `nm_health/rebuild.py`, `database.py`, `site.py` | Archive → inspections → SQLite / static site. |
| `nm_health/audit.py`, `spotcheck.py` | Check the site's assumptions against the city's records, and build an LLM spot-check packet ([docs/assumptions.md](docs/assumptions.md)). |
| `scripts/checks.sh` | The gate: ruff (all rules), mypy, complexity, shellcheck, ESLint/tsc/Prettier, pytest. Pre-commit and CI run it. |

Not affiliated with the City of Albuquerque.
