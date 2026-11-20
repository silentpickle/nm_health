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

A citation and the facts the article lists, never its prose:

| Field | What |
|---|---|
| `url`, `source`, `headline`, `published`, `author` | Where the article is and who published it, when |
| `weeks` | The week(s) its date line names ("Nov. 8-14"), years worked out from the publication date |
| `entries` | Each place as printed: `color` (GREEN / YELLOW / RED), `name`, `address`, `dates`, `classes` ("Class B"), `outcomes` (each result in a red place's Result line, with its date) |
| `captured_at` | When you saved the page |

The introduction, the color legend and every narrative paragraph are dropped. The JSON file the extension saves to
your Downloads folder does hold the article's body text: it's yours, never committed, and safe to delete once added.

## Recording articles

1. Install the extension once: open `chrome://extensions`, turn on Developer mode, click **Load unpacked**, and pick
   `tools/news-capture`.
2. Open an article from the tag page. A green **Save for nm_health** button appears at the bottom right of
   restaurant-inspection articles; click it. Chrome saves `nm-health-news-<article id>.json` to Downloads.
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
Result line with no place before it). Adding the same file twice is harmless.

## Not done yet

- The site doesn't read news links. Showing them is a change to the rule in [assumptions.md](assumptions.md) (the
  site states only what a county report on file says), so it waits for a decision on wording.
- News entries aren't matched to places. The Journal spells names and addresses its own way ("4301 The 25 NE" where
  the PDF prints "4301 THE LANE 25 NE"), so matching needs rules of its own, measured the way
  [place-identity.md](place-identity.md) measures the PDFs.

## Adding a source

Add its host to `[news] hosts` in `config.toml` and to `matches` in `tools/news-capture/manifest.json`. The parser
(`nm_health/news_capture.py`) expects the Journal's layout: a week line, then GREEN / YELLOW / RED headings. Another
paper needs its own reader.
