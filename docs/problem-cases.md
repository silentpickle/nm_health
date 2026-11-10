# Problem cases: the paper trail

Places whose records tripped up the site while building status today, closure lengths, the audit and the
spot-check, with every inspection on record and where it comes from, so each can be checked by hand. Generated from
the archive on 2026-11-10 (inspections since Nov 1, 2025).

**How to check a row**

- *PDF*: the link opens the archived weekly report; go to the page shown. Each place has a summary-table entry (its
  permit lines with Open/Closed, and one row per inspection) and a details block per inspection
  ("Date: … - #: <inspection ID> - Inspection Result: …").
- *Status feed*: look up any inspection ID in the saved feed snapshots (`start` is the inspection's start time):

  ```bash
  for f in data/feed/raw/*/*.json.gz; do gzcat "$f" | jq -c '.api_data.records[] | select(.ticket_detail_entry0=="RT-FOODEST-097628-2025") | {id: .ticket_detail_entry0, name: .ticket_detail_entry2, status: .ticket_detail_entry3, start: .ticket_detail_entry7, violations: .ticket_detail_entry9}'; done | sort -u
  ```

- *Site page*: `uv run nm-health site`, then open the path shown under each place.

The **Permit** column is the site's reading: an old-style inspection ID that is the permit number (`PT…`), else the
PDF summary table's permit line; "–" means the records name no permit. Commits are on branch `collector-and-site`.

## 1. Same-day inspections in the wrong order (fixed in `d72df5a`)

The site used to order inspections on one day by ID; the feed's start time now decides.

### Closed at 11:30, open again by 4:00 pm

**OJOS LOCOS SPORTS CANTINA**, 2105 LOUISIANA BLVD NE · site page: `site/place/ojos-locos-sports-cantina-2105-louisiana-blvd-ne.html`

The IDs sort the 11:30 closure last, so the site showed the place as closed. By time: closed 11:30, approved 4:00 pm, conditional approved 4:30 pm (two records in the afternoon, probably two permits).

**The site says now:** Open · Conditional Approved, per the Oct 9, 2026, 4:30 pm inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-10-09 | 11:30 | `RT-FOODEST-097628-2025` | – | Routine Food Establishment Inspection | Closure Re-Inspection Required | 17 | status feed only |
| 2026-10-09 | 16:00 | `RT-FOODEST-097595-2025` | – | Routine Food Establishment Inspection | Approved | 5 | status feed only |
| 2026-10-09 | 16:30 | `RT-FOODEST-096598-2026` | – | Routine Food Establishment Inspection | Conditional Approved | 6 | status feed only |

### Approved at 9:55, closed at 10:55

**Saint Martins Center**, 1201 3RD ST NW · site page: `site/place/saint-martins-center-1201-3rd-st-nw.html`

The reverse: the site showed Approved, but the closure came an hour later. Two different permit numbers, both food permits; the site now reads the whole place as closed (see section 6). No later inspection is on record.

**The site says now:** Closed since Aug 13, 2026, 10:55 am · by permit: Closure Re-Inspection Required (permit PT0054778, Aug 13, 2026, 10:55 am); Approved (permit PT0157951, Aug 13, 2026, 9:55 am).

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-08-13 | 09:55 | `PT0157951` | PT0157951 | Routine Food Establishment Inspection | Approved | 2 | status feed only |
| 2026-08-13 | 10:55 | `PT0054778` | PT0054778 | Routine Food Establishment Inspection | Closure Re-Inspection Required | 8 | status feed only |

### Closed and reopened the same afternoon

**NAAN & DOSA**, 6501 WYOMING BLVD NE, Unit B · site page: `site/place/naan-dosa-6501-wyoming-blvd-ne-unit-b.html`

Closure 1:06 pm, re-inspection conditional approved 2:07 pm, corrective-action visit approved the next day. The re-inspection has a new-style ID but the PDF files it under the same permit as the closure.

**The site says now:** Open · Approved, per the Oct 28, 2026 inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-10-27 | 13:06 | `PT0156723` | PT0156723 | Routine Food Establishment Inspection | Closure Re-Inspection Required | 11 | [2026-10-25_2026-10-31, p. 28](../data/archive/2026-10-25_2026-10-31_0e0b9708501f.pdf) |
| 2026-10-27 | 14:07 | `RT-FOODEST-101632-2026` | PT0156723 | Routine Food Establishment Inspection | Conditional Approved | 6 | [2026-10-25_2026-10-31, p. 28](../data/archive/2026-10-25_2026-10-31_0e0b9708501f.pdf) |
| 2026-10-28 | – | `CAC-Food-102040-2026` | PT0156723 | Corrective Action Compliance | Approved | 0 | [2026-10-25_2026-10-31, p. 27](../data/archive/2026-10-25_2026-10-31_0e0b9708501f.pdf) |

### The usual pattern: an old-style closure, a new-style re-inspection

**Taco Sal**, 9621 MENAUL BLVD NE · site page: `site/place/taco-sal-9621-menaul-blvd-ne.html`

The closure's ID is the permit number; the re-inspection that reopened it names no permit. The site treats an inspection with no permit number as the re-inspection of whatever failed before it (docs/assumptions.md).

**The site says now:** Open · Approved, per the Feb 24, 2026, 2:20 pm inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-02-24 | 11:40 | `PT0146962` | PT0146962 | Routine Food Establishment Inspection | Closure Re-Inspection Required | 20 | status feed only |
| 2026-02-24 | 14:20 | `RT-FOODEST-018046-2026` | – | Routine Food Establishment Inspection | Approved | 14 | status feed only |

## 2. Several results at the same minute

When the feed gives two results the same start time, the site lets the failure stand.

### Closure and conditional at 11:30

**Perico's Catering**, 1601 AVENIDA CESAR CHAVEZ SE · site page: `site/place/perico-s-catering-1601-avenida-cesar-chavez-se.html`

Two records at 11:30, neither naming a permit: one Closure, one Conditional Approved. The site reads it as closed and names the other result. Worth checking whether this is two permits or one inspection recorded twice. No later inspection on record.

**The site says now:** Closed since Sep 17, 2026, 11:30 am · Closure Re-Inspection Required, per the Sep 17, 2026, 11:30 am inspection (another record at the same time: Conditional Approved).

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-09-17 | 11:30 | `RT-FOODEST-088986-2026` | – | Routine Food Establishment Inspection | Conditional Approved | 13 | status feed only |
| 2026-09-17 | 11:30 | `RT-FOODEST-051827-2025` | – | Routine Food Establishment Inspection | Closure Re-Inspection Required | 15 | status feed only |

### Four results at 9:30, two approvals that afternoon

**KELLERS FARM STORE**, 2912 EUBANK BLVD NE · site page: `site/place/kellers-farm-store-2912-eubank-blvd-ne.html`

Four records at 9:30 (two Approved, one Unsatisfactory, one Closure, all retail, none naming a permit), then Approved at 2:00 and 2:15 pm. The site reads it as open again from the afternoon.

**The site says now:** Open · Approved, per the Sep 10, 2026, 2:15 pm inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-09-10 | 09:30 | `RT-RET-022672-2025` | – | Routine Retail Food Inspection | Approved | 3 | status feed only |
| 2026-09-10 | 09:30 | `RT-RET-058114-2025` | – | Routine Retail Food Inspection | Approved | 6 | status feed only |
| 2026-09-10 | 09:30 | `RT-RET-022674-2025` | – | Routine Retail Food Inspection | Unsatisfactory Re-Inspection required | 6 | status feed only |
| 2026-09-10 | 09:30 | `RT-RET-099999-2025` | – | Routine Retail Food Inspection | Closure Re-Inspection Required | 3 | status feed only |
| 2026-09-10 | 14:00 | `RT-RET-086407-2026` | – | Routine Retail Food Inspection | Approved | 2 | status feed only |
| 2026-09-10 | 14:15 | `RT-RET-086408-2026` | – | Routine Retail Food Inspection | Approved | 2 | status feed only |

### Two food permits at 9:30, one closed

**Bosque Brewing**, 10250 COTTONWOOD PARK NW · site page: `site/place/bosque-brewing-10250-cottonwood-park-nw.html`

Both inspections at 9:30 under consecutive permit numbers; one Approved, one Closure. Both are food permits, so the site reads the whole place as closed. No later inspection on record.

**The site says now:** Closed since Mar 13, 2026, 9:30 am · by permit: Closure Re-Inspection Required (permit PT0158662, Mar 13, 2026, 9:30 am); Approved (permit PT0158663, Mar 13, 2026, 9:30 am).

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-03-13 | 09:30 | `PT0158663` | PT0158663 | Routine Food Establishment Inspection | Approved | 3 | status feed only |
| 2026-03-13 | 09:30 | `PT0158662` | PT0158662 | Routine Food Establishment Inspection | Closure Re-Inspection Required | 16 | status feed only |

## 3. The city's Open/Closed disagrees with the rows (audit: `operational_status`)

### PDF says Open while listing a closure

**Bravo Cucina Italiana**, 2220 LOUISIANA BLVD NE · site page: `site/place/bravo-cucina-italiana-2220-louisiana-blvd-ne.html`

The Dec 14–20 report lists the Dec 17 closure under permit PT0082266 with Operational Status Open. The next report shows a corrective-action visit Dec 22 (Unsatisfactory) and approval Dec 24, so the Open was probably as of when the PDF was generated. The only one of 220 permits where the audit disagrees.

**The site says now:** Open · Approved, per the Apr 20, 2026, 2:45 pm inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2025-12-17 | 13:40 | `PT0082266` | PT0082266 | Routine Food Establishment Inspection | Closure Re-Inspection Required | 7 | [2025-12-14_2025-12-20, p. 17](../data/archive/2025-12-14_2025-12-20_fc1b3048dffd.pdf) |
| 2025-12-22 | – | `CAC-Food-118114-2025` | PT0082266 | Corrective Action Compliance | Unsatisfactory Re-Inspection required | 0 | [2025-12-21_2025-12-27, p. 5](../data/archive/2025-12-21_2025-12-27_b34ea77b33c8.pdf) |
| 2025-12-24 | 10:54 | `RT-FOODEST-116919-2025` | PT0082266 | Routine Food Establishment Inspection | Approved | 5 | [2025-12-21_2025-12-27, p. 4](../data/archive/2025-12-21_2025-12-27_b34ea77b33c8.pdf) |
| 2026-04-20 | 13:00 | `RT-FOODEST-118834-2025` | – | Routine Food Establishment Inspection | Conditional Approved | 7 | status feed only |
| 2026-04-20 | 14:45 | `PT0082267` | PT0082267 | Routine Food Establishment Inspection | Approved | 5 | status feed only |

## 4. Parser misses

### A violation behind a stray dot; a recap counted as rodents (fixed in `1ad8050`, `8b9446e`)

**CALIFORNIA DEL NORTE INC**, 1415 4TH ST SW, Unit H · site page: `site/place/california-del-norte-inc-1415-4th-st-sw-unit-h.html`

The Sep 25 corrective-action visit's details start ". Violation: Result of a Complaint"; the dot hid the heading and the visit read 0 violations (found by the LLM spot-check). Once read, its text recaps the Sep 21 mice droppings as cleaned up; corrective-action visits no longer count as pest citations. Also: the summary calls the permit a Retail Food Establishment, but the Sep 25 details say "Mobile Food Unit Class A". Not fixed: "Violation: Result of a Complaint" is the city's tag for a complaint-triggered inspection, not a violation, yet the site counts it as one (one of Sep 21's six, and Sep 25's only one), as the second spot-check pointed out.

**The site says now:** Open · Approved, per the Sep 25, 2026 inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-09-21 | – | `COM-RET-092636-2026` | PT0132485 | Complaint Retail Food Inspection | Closure Re-Inspection Required | 6 | [2026-09-20_2026-09-26, p. 9](../data/archive/2026-09-20_2026-09-26_4526d9bed974.pdf) |
| 2026-09-25 | – | `CAC-Food-091506-2026` | PT0132485 | Corrective Action Compliance | Approved | 1 | [2026-09-20_2026-09-26, p. 8](../data/archive/2026-09-20_2026-09-26_4526d9bed974.pdf) |

### A hyphenated permit number read as the previous place's (fixed in `0943917`)

**FROST, A GELATO SHOPPE-PT0160304**, 2201 Q ST NE, Unit 9-A · site page: `site/place/frost-a-gelato-shoppe-pt0160304-2201-q-st-ne-unit-9-a.html`

The permit line "(Permit # - FOODEST-2025-00423)" didn't match the parser, so FROST's rows took the permit of the place listed before it, and the site said one of two permits was closed. It is one permit: closed Jan 2, Unsatisfactory on the Jan 5 follow-up, approved Jan 8.

**The site says now:** Open · Approved, per the Jan 8, 2026, 11:00 am inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-01-02 | 11:00 | `RT-FOODEST-004640-2025` | FOODEST-2025-00423 | Routine Food Establishment Inspection | Closure Re-Inspection Required | 29 | [2025-12-28_2026-01-03, p. 7](../data/archive/2025-12-28_2026-01-03_0e6eeb05fe07.pdf) |
| 2026-01-05 | – | `CAC-Food-002225-2026` | FOODEST-2025-00423 | Corrective Action Compliance | Unsatisfactory Re-Inspection required | 0 | [2026-01-04_2026-01-10, p. 27](../data/archive/2026-01-04_2026-01-10_ad9534c41b86.pdf) |
| 2026-01-08 | 11:00 | `RT-FOODEST-000191-2026` | FOODEST-2025-00423 | Routine Food Establishment Inspection | Approved | 5 | [2026-01-04_2026-01-10, p. 26](../data/archive/2026-01-04_2026-01-10_ad9534c41b86.pdf) |

## 5. Summary-table rows under the wrong permit (handled in `9dddd45`)

In these reports a row sits under another permit's line; the details pages show which is which. The site now trusts an old-style ID (the permit number itself) over the row's position.

### Food permit Closed, retail permit Open, rows swapped

**QUICK TRACK 93**, 2625 WYOMING BLVD NE · site page: `site/place/quick-track-93-2625-wyoming-blvd-ne.html`

Summary, p. 38: "Food Establishment (Permit # - PT0160313) - Operational Status – Closed" with the row for PT0160314 (retail, Approved) under it, and the retail permit's line (Open) with PT0160313's closure row under it. The details confirm PT0160313 is the food permit and was closed. This is also the city's only place, of 42 listed with several permits, with one permit Closed and another Open: the convenience-store case.

**The site says now:** Open · Approved, per the Jan 23, 2026, 9:30 am inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-01-08 | 11:10 | `PT0160314` | PT0160314 | Routine Retail Food Inspection | Approved | 2 | [2026-01-04_2026-01-10, p. 38](../data/archive/2026-01-04_2026-01-10_ad9534c41b86.pdf) |
| 2026-01-08 | 11:10 | `PT0160313` | PT0160313 | Routine Food Establishment Inspection | Closure Re-Inspection Required | 11 | [2026-01-04_2026-01-10, p. 38](../data/archive/2026-01-04_2026-01-10_ad9534c41b86.pdf) |
| 2026-01-23 | 09:30 | `RT-FOODEST-002091-2026` | – | Routine Food Establishment Inspection | Approved | 4 | status feed only |

### Food and retail rows swapped

**Allsup's #102460**, 9501 GIBSON BLVD SW · site page: `site/place/allsup-s-102460-9501-gibson-blvd-sw.html`

Same report, same swap: each permit line has the other permit's row under it. Both permits passed, so the status reading doesn't change.

**The site says now:** Open · by permit: Approved (Food Establishment PT0161595, Jan 9, 2026); Conditional Approved (Retail Food Establishment PT0161594, Jan 9, 2026).

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-01-09 | – | `PT0161594` | PT0161594 | Routine Food Establishment Inspection | Conditional Approved | 5 | [2026-01-04_2026-01-10, p. 6](../data/archive/2026-01-04_2026-01-10_ad9534c41b86.pdf) |
| 2026-01-09 | – | `PT0161595` | PT0161595 | Routine Retail Food Inspection | Approved | 4 | [2026-01-04_2026-01-10, p. 6](../data/archive/2026-01-04_2026-01-10_ad9534c41b86.pdf) |

### A row under the other permit; the place split in two by address spelling

**SERGIOS BAKERY AND CAFE**, 2740 WYOMING STE #8 BLVD NE · site page: `site/place/sergios-bakery-and-cafe-2740-wyoming-ste-8-blvd-ne.html`

Dec 28 – Jan 3 report: PT0126278's row sits under PT0126277's line. Separately, this place's records spell the address two ways, so its history is split across two site pages; this page has the PDF records.

**The site says now:** Open · Approved, per the Sep 22, 2026 inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2025-12-30 | 09:20 | `PT0126278` | PT0126278 | Routine Retail Food Inspection | Closure Re-Inspection Required | 12 | [2025-12-28_2026-01-03, p. 22](../data/archive/2025-12-28_2026-01-03_0e6eeb05fe07.pdf) |
| 2025-12-30 | – | `CAC-Food-119823-2025` | PT0126278 | Corrective Action Compliance | Unsatisfactory Re-Inspection required | 0 | [2025-12-28_2026-01-03, p. 24](../data/archive/2025-12-28_2026-01-03_0e6eeb05fe07.pdf) |
| 2025-12-30 | – | `CAC-Food-119827-2025` | PT0126277 | Corrective Action Compliance | Unsatisfactory Re-Inspection required | 0 | [2025-12-28_2026-01-03, p. 22](../data/archive/2025-12-28_2026-01-03_0e6eeb05fe07.pdf) |
| 2026-01-06 | 11:20 | `RT-FOODEST-119841-2025` | PT0126277 | Routine Food Establishment Inspection | Approved | 1 | [2026-01-04_2026-01-10, p. 42](../data/archive/2026-01-04_2026-01-10_ad9534c41b86.pdf) |
| 2026-01-06 | 23:20 | `RT-RET-119839-2025` | PT0126278 | Routine Retail Food Inspection | Approved | 1 | [2026-01-04_2026-01-10, p. 42](../data/archive/2026-01-04_2026-01-10_ad9534c41b86.pdf) |
| 2026-09-22 | – | `COM-FOODES-089986-2026` | PT0126277 | Complaint Food Establishment Inspection | Conditional Approved | 10 | [2026-09-20_2026-09-26, p. 38](../data/archive/2026-09-20_2026-09-26_4526d9bed974.pdf) |
| 2026-09-22 | – | `COM-RET-089988-2026` | PT0126278 | Complaint Retail Inspection | Approved | 6 | [2026-09-20_2026-09-26, p. 39](../data/archive/2026-09-20_2026-09-26_4526d9bed974.pdf) |
| 2026-09-22 | – | `CAC-Food-090323-2026` | PT0126277 | Corrective Action Compliance | Approved | 1 | [2026-09-20_2026-09-26, p. 38](../data/archive/2026-09-20_2026-09-26_4526d9bed974.pdf) |

### (the other half of Sergio's)

**SERGIOS BAKERY AND CAFE**, 2740 WYOMING BLVD NE · site page: `site/place/sergios-bakery-and-cafe-2740-wyoming-blvd-ne.html`

Feed records under the other spelling. A Jun 11 retail closure here is followed only by a Jun 17 food re-inspection with no permit number, which the site lets replace it. Open question: should these two pages be one place?

**The site says now:** Open · Conditional Approved, per the Jun 17, 2026, 10:45 am inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2025-12-30 | 09:20 | `PT0126277` | PT0126277 | Routine Food Establishment Inspection | Closure Re-Inspection Required | 14 | status feed only |
| 2026-06-11 | 12:00 | `RT-FOODEST-001021-2026` | – | Routine Food Establishment Inspection | Closure Re-Inspection Required | 17 | status feed only |
| 2026-06-11 | 12:00 | `RT-RET-001020-2026` | – | Routine Retail Food Inspection | Closure Re-Inspection Required | 23 | status feed only |
| 2026-06-17 | 10:45 | `RT-FOODEST-056008-2026` | – | Routine Food Establishment Inspection | Conditional Approved | 6 | status feed only |

## 6. Several permits at one place (handled in `9dddd45`)

### Food service closed, retail open

**DRURY INN & SUITES ALBUQUERQUE**, 4310 THE 25 WAY NE · site page: `site/place/drury-inn-suites-albuquerque-4310-the-25-way-ne.html`

Retail permit approved 7:15 am, food permit closed 8:00 am. The only place in the window that reads "Food service closed, retail open". No later inspection on record.

**The site says now:** Food service closed since Jun 15, 2026, 8:00 am, retail open · by permit: Closure Re-Inspection Required (permit PT0051883, Jun 15, 2026, 8:00 am); Approved (permit PT0140689, Jun 15, 2026, 7:15 am).

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-06-15 | 07:15 | `PT0140689` | PT0140689 | Routine Retail Food Inspection | Approved | 0 | status feed only |
| 2026-06-15 | 08:00 | `PT0051883` | PT0051883 | Routine Food Establishment Inspection | Closure Re-Inspection Required | 5 | status feed only |

### Three departments, three permits, one morning

**ALBERTSONS #911**, 2801 EUBANK BLVD NE, Unit A · site page: `site/place/albertsons-911-2801-eubank-blvd-ne-unit-a.html`

Deli, bakery and meat permits (PT0043512, PT0043515, PT0043513, consecutive numbers) inspected an hour apart. All passed; the case the second model raised about one permit's closure hiding behind another's pass.

**The site says now:** Open · Approved, per the Oct 27, 2026, 11:30 am inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-08-26 | 13:15 | `RT-RET-057653-2025` | – | Routine Retail Food Inspection | Approved | 1 | status feed only |
| 2026-10-27 | 09:30 | `RT-RET-057734-2025` | PT0043512 | Routine Retail Food Inspection | Approved | 4 | [2026-10-25_2026-10-31, p. 6](../data/archive/2026-10-25_2026-10-31_0e0b9708501f.pdf) |
| 2026-10-27 | 10:30 | `RT-RET-057696-2025` | PT0043515 | Routine Retail Food Inspection | Approved | 4 | [2026-10-25_2026-10-31, p. 7](../data/archive/2026-10-25_2026-10-31_0e0b9708501f.pdf) |
| 2026-10-27 | 11:30 | `RT-RET-057642-2025` | PT0043513 | Routine Retail Food Inspection | Approved | 3 | [2026-10-25_2026-10-31, p. 6](../data/archive/2026-10-25_2026-10-31_0e0b9708501f.pdf) |

## 7. Same-day order with no times (audit: `untimed_order`)

### Unsatisfactory and Approved on one day, neither timed

**Golden Pride Legacy LLC**, 3720 JUAN TABO BLVD NE · site page: `site/place/golden-pride-legacy-llc-3720-juan-tabo-blvd-ne.html`

Two complaint inspections on Sep 21 under the same permit, with no feed times. The site assumes the failure came first, so it reads approved. ("Golden Pride Legacy LLC" is a legal name shared by four stores; the site keeps them apart by address.)

**The site says now:** Open · Approved, per the Sep 21, 2026 inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-05-06 | 13:00 | `RT-FOODEST-081374-2025` | – | Routine Food Establishment Inspection | Conditional Approved | 7 | status feed only |
| 2026-09-21 | – | `COM-FOODES-089829-2026` | PT0043523 | Complaint Food Establishment Inspection | Unsatisfactory Re-Inspection required | 9 | [2026-09-20_2026-09-26, p. 20](../data/archive/2026-09-20_2026-09-26_4526d9bed974.pdf) |
| 2026-09-21 | – | `COM-FOODES-089858-2026` | PT0043523 | Complaint Food Establishment Inspection | Approved | 6 | [2026-09-20_2026-09-26, p. 19](../data/archive/2026-09-20_2026-09-26_4526d9bed974.pdf) |

## 8. Violation counts differ from the city's

### 16 listed on the site, 13 in the feed

**RED ROOF INN**, 2015 MENAUL BLVD NE · site page: `site/place/red-roof-inn-2015-menaul-blvd-ne.html`

The site counts each bulleted item in the PDF; the city's feed counts the "Violation:" headings (three items under Operation and Maintenance, two under Personal Cleanliness). Not fixed: a choice of which count to show.

**The site says now:** Closed since Oct 28, 2026, 8:05 am · Closure Re-Inspection Required, per the Oct 28, 2026, 8:05 am inspection.

| Date | Time | Inspection ID | Permit | Type | Status | Violations | Source |
|---|---|---|---|---|---|---|---|
| 2026-10-28 | 08:05 | `RT-FOODEST-075528-2025` | PT0152707 | Routine Food Establishment Inspection | Closure Re-Inspection Required | 16 | [2026-10-25_2026-10-31, p. 30](../data/archive/2026-10-25_2026-10-31_0e0b9708501f.pdf) |
