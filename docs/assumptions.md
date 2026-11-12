# What the site assumes, and how to check it

## The rule: the city's weekly reports make every statement

The public site states only what a City of Albuquerque weekly inspection report on file says, and links every
statement to the page of that report (a byte-for-byte copy under `reports/`). "Don't shoot the messenger": the city
makes the declaration, the site repeats it. Incomplete is better than wrong, and the record grows by one report a week.

- An inspection appears only if a weekly report on file prints it, dated inside the week the report covers (one
  report prints a typo date, "1/29/2026" in its Jan 27-31, 2025 week; it stays off).
- A place's status is the city's own "Operational Status" line for each permit, quoted from the latest report that
  lists it, followed by the latest result in the reports on file.
- The status feed makes no statement and is not affiliated with the weekly reports. It has no document a reader can
  open, and it lists routine inspections only: no corrective-action visits and no complaint inspections. The site
  uses it for one thing, the coordinates of map dots (a location anyone can check against the city's system today).
  Its start times, violation counts and feed-only inspections stay out of every page; same-day order therefore falls
  back to the untimed rule (a failure is assumed to come first). Reason: once a place passes, the inspector leaves, so a pass
  is the last word of the day; a failure the same day came before it, and the place was fixed and re-inspected. `nm-health audit` still reads the full feed to
  check it against the reports.
- A closure's length is stated only when every day between the closure and the reopening inspection is in a report on
  file; across a gap the site says the place may have reopened sooner.
- "Reopened" means what a closure's length already means (`signals.closed_spells`): after a closure, the first later
  inspection with a result that lets the place operate (approved, conditional, or unsatisfactory: a red sticker, but
  open). It doesn't count when the reopening result is another permit's and the closed permit's closure still stands
  (`signals.standing`). On This week, "Reopened since the prior report" lists places closed before the week's first
  day (so in an earlier report on file, and still closed when the week began) whose reopening inspection is dated
  inside the week; the week is the page's own (the newest inspection date and the six days before it), so it holds
  the same way when the newest week's report isn't on file yet. On Last month and All time, "Reopened after a
  closure" lists reopenings dated inside the range, the closure before or inside it. Each card gives both dates, the
  closure's length as above, and links both reports' pages. `places.json` carries each page's list under
  `reopened`, keyed by page file, for tracking.

## Checking the assumptions

The statements rest on assumptions about how the city records inspections. The unit tests prove the code does what we intend; they
can't prove the intent matches the city. `uv run nm-health audit` checks that against the real archive and feed and
prints, for each assumption, how many cases it looked at and the ones that disagree. It reports and never fails:
a person judges the disagreements.

| Assumption | Check | What it compares |
|---|---|---|
| Only a Closure means closed; an Unsatisfactory place stays open (red sticker) | `operational_status` | Each PDF permit line's own "Operational Status – Open/Closed" against the latest result listed under it |
| The feed's start time is when the inspection happened | `feed_times` | Flags times of exactly 00:00, a likely placeholder |
| Results at the same minute are separate permits, so the failure stands | `same_minute` | Permit numbers of same-minute records with a failure among them |
| Each permit's latest result stays in force until that permit is inspected again; an inspection with no permit number (most re-inspections since late 2025) replaces every earlier result; when permits' results differ, status today lists each one and says nothing about the place as a whole | `same_minute` (partly) | Permits are known from the PDF's summary table or an old-style ID that is the permit number; the feed names no permit |
| An untimed corrective-action visit came after that day's routine inspection | `follow_up_order` | Feed times, when both sides have one |
| With no time, a same-day failure came before the pass | `untimed_order` | Lists the days where this guess decides the order |
| The PDF and the feed agree on each inspection's status | `feed_status` | Status of every inspection found in both |
| A report prints only inspections from the week it covers | `dates_in_week` | Each PDF inspection's date against its report's week (the site skips any outside it) |
| A closure with no reopening on record for weeks is a missing record, not a months-long closure | `long_closures` | Lists closures in force over `[audit] long_closure_days` (14) with a second opinion from `nm-health judge` |

## A second opinion from any LLM

The audit only checks what we thought to write a rule for. `uv run nm-health spotcheck` prints a packet for a model to
read instead: a prompt, this document, and for six sampled places (`[spotcheck] places` in config.toml) every statement
the site makes, numbered, with the city's records for those places: the status-feed rows and each inspection's
summary rows and details from the weekly PDF, with emails and phone numbers removed. The sample always includes a
place reopened after a closure, one closed today, one with roaches or rodents, one with several results in a day and an
ordinary one, preferring places whose inspector notes are on file, so the claims can be checked against the PDF.

No API key is involved: copy it into any chat you're signed in to and read the answer.

```bash
uv run nm-health spotcheck | pbcopy
```

The sample changes daily; `--seed N` repeats a packet (the seed is printed at its top) and `--places N` changes the
size. A packet of six places is about 50 KB.

## A second opinion on long closures

A restaurant closed for months is unusual; usually its reopening is in a weekly report we don't hold. `uv run
nm-health judge` (local only: it needs your `agy` login) asks, for each closure in force over 14 days, two questions
with typed answers checked against a JSON schema: is the business restaurant-only (yes / no / unsure, with a reason),
and, from a web search, is it operating now (operating / closed / unknown, with the evidence). Names that say the place
does more than serve food (hotel, inn, suites, school, academy, gas station, 7-Eleven, grocery...) are answered "no"
without asking. Answers are saved in `data/judgements.json` (commit it) and asked again only when a new closure is
recorded. `nm-health audit` lists them under `long_closures`, restaurant-only first. None of this reaches the public
site: it tells you where to dig.

## Results on 2026-11-10 (whole archive, 2020–2026)

- `operational_status`: 219 of 220 permits agree, including 8 Unsatisfactory permits the city lists Open. The one
  that disagrees (Bravo Cucina, Dec 2025) was closed on Dec 17 and reopened on Dec 22 per our records. The weekly PDF
  for Dec 14–20 already says Open, so its Operational Status seems to reflect when the PDF was generated, not the
  week's end.
- `feed_times`: 372 of 13,508 times are 00:00, all from 2020 to Oct 2025. None fall in the site's 12-month window yet.
  Ordering still treats 00:00 as a real time; if one appears in the window, treat it as unknown.
- `same_minute`: 30 same-minute groups with a failure. 11 are confirmed separate permits; 19 can't be confirmed
  because a feed-only record has no permit number. None are the same permit.
- `follow_up_order`: can't be checked. None of the 48 corrective-action visits has a feed time.
- `untimed_order`: 3 of 1,668 same-day groups depend on the guess. One is in the window: Golden Pride Legacy LLC,
  Sep 21, 2026 (Approved and Unsatisfactory, neither timed), which the site reads as failed, then approved.
- `feed_status`: all 290 inspections in both sources agree.

Places can hold several permits at once, one per operation: 275 of 317 places with more than one known permit had
different permits inspected on the same day (Albertsons #911 holds PT0043512 to PT0043515: deli, bakery, meat). The site
quotes each permit's "Operational Status" line as the city printed it in the latest report listing the place, and makes
no claim about the place as a whole. Permits come from an old-style inspection ID, which is the permit number, else the
PDF's summary table; the ID wins because the table now and then files a row under the wrong permit (5 of 173 rows: Quick
Track 93, Allsup's #102460, Sergio's Bakery).

Not checked: that a place's name and address identify one place, that an inspection with no permit number re-inspected
what failed before it, and that no reopening inspection is missing from the records (a missing one would make a closure
look longer than it was).
