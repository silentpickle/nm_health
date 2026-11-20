# News links

Newspaper write-ups of the city's weekly inspection reports, recorded for the weeks the county archive has no PDF
for. They live apart from the archive (`data/news/links.jsonl`) and never override it.

Today's one source is the Albuquerque Journal's weekly "businesses red-tagged" article
([tag page](https://www.abqjournal.com/tag/restaurant%20inspections)). Each restates one city report: the week, then
every place under GREEN, YELLOW and RED with its address and dates, and a Result line for each red place. The series
starts with the week of Nov 30 to Dec 6, 2025. Of the 50 weeks from then to Nov 14, 2026, 42 have no county PDF on
file (Nov 30 to Dec 13, 2025; Jan 11 to Sep 19, 2026; Sep 27 to Oct 24, 2026).

## The rule: a county report always wins

An entry from a news link is usable only when none of its dates falls in a week an archived county PDF covers
(`news.usable_entries`). A red place is dated by its Result line; an entry printed with no date stands for every day
of the article's week. Usability is worked out each time the links are read, never stored, so a PDF recovered later
(say by `backfill-wayback`) retires the news entries for its week by itself. The record is kept either way.

Archived PDFs with no week on file (`unknown-week_…`) can't count as covered; `news list` names them so you can
check those days by hand.

## Why there is no crawler

Fetching the Journal's pages works, and its robots.txt allows `/` for ordinary agents, but the notice at the top of
that file restricts automated collection, naming archiving and "derivative databases of our reporting". So nothing in
this repo fetches the Journal. The browser extension reads only the page you have open, and only when you click.

## What a record keeps

A citation, what the article lists, and each red-listed place's description as printed:

| Field | What |
|---|---|
| `url`, `source`, `headline`, `published`, `author` | Where the article is and who published it, when |
| `weeks` | The week(s) its date line names ("Nov. 8-14"), years worked out from the publication date |
| `entries` | Each place as printed: `color` (GREEN / YELLOW / RED), `name`, `address`, `dates`, `classes` ("Class B"), `outcomes` (each result in a red place's Result line, with its date), `notes` (a red place's description paragraphs, as printed) |
| `captured_at` | When you saved the page |

The introduction and the color legend are dropped. The paper describes only red-listed places, so GREEN and YELLOW
entries (passing and conditional grades) carry no notes: a name, address and date is all there is to record. The descriptions are the paper's words (the owner's decision of
Nov 20, 2026, knowing the Journal's notice): the site only ever shows them as a quote, attributed to the paper, never
as the inspector's notes. The JSON files the extension saves to Downloads hold the article's whole body; keep them
until you're sure nothing more is wanted from them.

## Recording articles

1. Install the extension once: open `chrome://extensions`, turn on Developer mode, click **Load unpacked**, and pick
   `tools/news-capture`.
2. Open an article from the tag page. A green **Save for nm_health** button appears at the bottom right of
   restaurant-inspection articles; click it. Chrome saves `nm-health-news-<article id>.json` to Downloads. Past the
   Journal's free-article limit the paywall hides the text: the button then says "No article text on the page" and
   saves nothing. Come back to that article later.
3. Record what you saved, then check it:

   ```bash
   uv run nm-health news add ~/Downloads/nm-health-news-*.json
   ```

   ```bash
   uv run nm-health news list
   ```

4. Commit `data/news/links.jsonl`.

`news add` prints one line per file: `NEW`, `UPDATED` (the facts changed since the last capture), `same`, or
`SKIPPED` with the reason (wrong site, no week line, not JSON). Below each record it says how much of it the county
archive leaves usable, and warns about any line that looked like a fact but didn't read (a place with no date, a
Result line with no place before it). Adding the same file twice is harmless. The Journal's own typos (a missing
parenthesis around a date or a "Class C" note) still read; "Editor's note" lines are skipped.

`news list` ends with the weeks that have neither a county PDF nor a news link, from your earliest news link's week to
the archive's latest day: the articles still worth saving.

## On the site

The site folds usable entries into the places' histories (`nm_health/news_fold.py`), under the rule in
[assumptions.md](assumptions.md): only what a person can easily check in a published source meant for people.

- Each entry becomes the city's status for its date (GREEN Approved, YELLOW Conditional Approved, a red place's
  results as the city words them); a place listed twice the same day with one status is one inspection.
- Every statement links to the article, our saved record of it (`news/<slug>.html`, which lists what we recorded and
  which entries are used), and an Internet Archive copy.
- A Journal place joins another place at the same street number and street name (types and units dropped) when the
  names agree, store numbers and "LLC" aside, or one starts the other; never one that would bridge two places kept
  apart (place-identity.md, M9 and M10). The place page says how the Journal printed it. Every other Journal place
  gets its own page, under the Journal's spelling.
- A red place's description goes with the result it explains (its first failing one), quoted on the place page as
  the paper's words. Each sentence is tagged as an inspector's observation would be (`nm_health/tags.py`), so pest
  readings ("Rodents, live") and the roaches-or-rodents flags cover these weeks too, credited to the paper. Measured
  on the 13 red places both a city report and an article describe: roaches 1 of 1 and rodents 2 of 2 agree with the
  city's notes, none extra; sanitizer 6/6 and training 8/8 agree; the paper leaves out permits and pest paperwork,
  and its wording misses 5 of 6 date-marking cites.
- `uv run nm-health site` reads `data/news/links.jsonl`; the daily site build does the same.

`uv run nm-health news archived` looks up an Internet Archive copy for each link that has none and saves its address
in the record. It only looks: it never asks the Archive to make a copy. As of Nov 20, 2026 all 37 articles have one.

## Adding a source

Add its host to `[news] hosts` in `config.toml` and to `matches` in `tools/news-capture/manifest.json`. The parser
(`nm_health/news_capture.py`) expects the Journal's layout: a week line, then GREEN / YELLOW / RED headings. Another
paper needs its own reader.
