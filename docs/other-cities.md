# Other cities and states: where their inspection data lives

Written 2026-11-14 for whoever adds a second city. It keeps what the multi-region prototype (branch
`wip/multi-region-prototype`) found about other jurisdictions, with its mistakes fixed, and drops its adapters. Every
section says what was checked against the source on 2026-11-14 and what was not. Treat anything marked
**(unverified)** as a lead, not a fact.

**In short**

- Socrata portals are the easy case: Chicago, NYC, NY State, King County, San Francisco and Austin all publish current
  data on SODA 2.x with no login. Dallas stopped in 2024; Kansas City and Minneapolis are not on Socrata.
- Only **Chicago** and **NY State** carry the inspector's own words. NYC, King County, San Francisco, Las Vegas and
  Austin give violation codes and standard descriptions, or only a score.
- History differs a lot. Chicago keeps everything since 2010. NYC keeps three years and only for restaurants still
  open; Austin keeps three years. A closed NYC restaurant drops out of the data, the same disappearing record this
  project exists to fix for Albuquerque.
- No Socrata source gives a document per inspection, so a site that links every statement to a document
  (docs/assumptions.md) would have to link to a query or a lookup page instead.
- MyHealthDepartment (Oregon, Orange County, Virginia, San Francisco's lookup) turns away scripts (HTTP 403 on
  2026-11-14). Nothing about its API was confirmed.

| Jurisdiction | Platform, ID | Newest inspection on 2026-11-14 | History kept | Inspector's words? |
|---|---|---|---|---|
| Chicago | Socrata `4ijn-s7e5` | Nov 13, 2026 | 2010 on, all | Yes (`violations`) |
| New York City | Socrata `43nn-pn8j` | Nov 10, 2026 | 3 years, open restaurants only | No |
| New York State (outside NYC) | Socrata `2hcc-shji` | Nov 6, 2026 | 2005 on (active facilities) | Yes (`inspection_comments`) |
| King County / Seattle | Socrata `r878-4sxa` | Nov 12, 2026 | 2021 on | No |
| San Francisco | Socrata `tvy3-wexg` | Nov 13, 2026 | 2024 on (older years in other datasets) | No |
| Austin | Socrata `ecmv-9xxi` | Oct 10, 2026 | 3 years | No (score only) |
| Dallas | Socrata `dri5-wcct` | Jan 2024 | Stopped | Not checked |
| Las Vegas / Southern Nevada | ArcGIS feature layer | Jun 2, 2024 | Stopped | No (codes only) |
| Oregon, Multnomah County | MyHealthDepartment | Not checked | Not checked | Not checked |
| Orange County, CA | MyHealthDepartment | Not checked | Not checked | Not checked |

## Albuquerque, for comparison

- **Who inspects.** The City of Albuquerque Environmental Health Department covers the city only. Unincorporated
  Bernalillo County has its own inspectors (Bernalillo County Planning and Development Services, Health Protection),
  and this project does not cover them. The rest of the state is the New Mexico Environment Department (NMED), whose
  own FAQ says it has no jurisdiction in Albuquerque or Bernalillo County.
  [NMED FAQ](https://www.env.nm.gov/foodprogram/food-faqs/). The county program is confirmed only by a third-party
  directory (AFDO) **(unverified on a county page)**.
- **NMED has no online inspection lookup.** A 2018 Santa Fe New Mexican report says the state dropped its planned
  online results, and none was found on 2026-11-14. Records come by IPRA request (docs/ipra.md).
- **The weekly PDF lags about a week.** The report live on 2026-11-14 covers Nov 1–7, 2026 and was created Nov 11,
  so an inspection reaches it 4 to 10 days later.
- **The city's old open data were flat files, not Socrata.** `https://data.cabq.gov/business/foodinspections/`
  holds yearly CSV/XML files (UTF-16, tab-separated) for FY2009 to FY2020 under `History/`. The last was modified
  August 2020, and the current-year file has a header and no rows. One row per checklist item, with
  `RESULT_DESC`, `VIOLATION_DESC` and an `INSPECTION_MEMO` that does carry inspector notes on some rows (e.g.
  "OBSERVED HAND WASHING SINKS NOT PROPERLY STOCKED OR CONVENIENTLY LOCATED."). The prototype's story that
  Albuquerque's Socrata feed lagged 6 to 12 weeks and stripped the notes could not be confirmed and is dropped.
  These files are the place to look if inspections from FY2009 to FY2020 are ever wanted.
- **Info Connect** (`albuquerquenm-cc.connect.socrata.com`) is a Tyler app, not a Socrata open-data dataset. This
  project already reads it as the status feed (`[feed]` in `config.toml`): status, violation count, coordinates, no
  violation text. It is not in the Socrata catalog, so the SODA notes below don't apply to it.

Checked 2026-11-14: [data.cabq.gov listing](https://data.cabq.gov/business/foodinspections/),
[results page](https://www.cabq.gov/environmentalhealth/food-safety/restaurant-inspection-results), live PDF.

## Working with Socrata

**Endpoints (SODA 2.x).** Data: `GET https://{domain}/resource/{id}.json` with SoQL parameters `$select`, `$where`,
`$order`, `$group`, `$limit`, `$offset`. The default `$limit` is 1000, so page with `$offset`. Metadata:
`GET https://{domain}/api/views/{id}.json` gives `name`, `description`, `rowsUpdatedAt` (Unix seconds) and
`columns[]` with `fieldName` and `dataTypeName`. Read `description`: it states the history window, and that is
where NYC's and Austin's three-year limits are written. To find datasets:
`https://api.us.socrata.com/api/catalog/v1?domains={domain}&q={words}`.

**Tokens and limits.** SODA 2.x works with no token, but tokenless requests share a smaller limit tied to your IP
and get HTTP 429 when throttled. Requests with an app token in the `X-App-Token` header are not throttled unless
abusive. SODA 3.0 (`/api/v3/views/{id}/query.json`) requires a token or a login. The docs give no numbers.
[App tokens](https://dev.socrata.com/docs/app-tokens.html), [endpoints](https://dev.socrata.com/docs/endpoints.html).

**Freshness.** Use the newest inspection date and ignore dates in the future:

```bash
curl -s -G "https://data.sf.gov/resource/tvy3-wexg.json" \
  --data-urlencode '$select=max(inspection_date)' \
  --data-urlencode "\$where=inspection_date <= '2026-11-14'"
```

Without the `$where`, San Francisco answers 2031-05-16 (one typo row). Don't use `rowsUpdatedAt` or the `:updated_at`
system field: they say when rows were last loaded, and a full reload of stale data looks fresh.

**Text search is case-sensitive.** `like` matches case exactly. On Chicago, `violations like '%roach%'` finds 3,644
rows; `upper(violations) like '%ROACH%'` finds 7,441. Always compare in upper case.

**Rows are not always inspections.** Chicago has one row per inspection with violations joined by ` | `. NYC, King
County and NY State have one row per violation; group by facility ID and date (and King County's
`inspection_serial_num`) to rebuild an inspection.

## Chicago

- **Source.** Socrata, `data.cityofchicago.org`, dataset `4ijn-s7e5` (Food Inspections), Chicago Department of
  Public Health. Rows updated daily (most recent load 10:07 UTC on Nov 14; the prototype's "06:00 CST" is
  **unverified**).
- **History.** Every inspection since January 1, 2010 (318,396 rows). Nothing is dropped.
- **Fields.** `inspection_id`, `license_` (license number), `dba_name`, `aka_name`, `facility_type`, `risk`,
  `address`, `zip`, `inspection_date`, `inspection_type`, `results`, `violations`, `latitude`, `longitude`.
- **Inspector's words: yes.** `violations` is "NN. TITLE - Comments: …" items joined by ` | `, with the inspector's
  text after "Comments:", e.g. "38. INSECTS, RODENTS, & ANIMALS NOT PRESENT - Comments: 6-501.111: OBSERVED
  APPROXIMATELY 6 BIG FLIES…".
- **Results.** `Pass`, `Pass w/ Conditions`, `Fail`, plus non-inspections: `Out of Business`, `No Entry`,
  `Not Ready`, `Business Not Located`.
- **Pest items.** The numbering changed with the July 1, 2018 procedure change (noted in the dataset description).
  Since then: 38 "INSECTS, RODENTS, & ANIMALS NOT PRESENT". Before: 13 "NO EVIDENCE OF RODENT OR INSECT INFESTATION…",
  18 "…OUTER OPENINGS PROTECTED/RODENT PROOFED…", 19 "OUTSIDE GARBAGE WASTE GREASE AND STORAGE AREA; CLEAN, RODENT
  PROOF…". Other current items seen: 36 thermometers, 54 garbage and refuse, 55 physical facilities, 57 food handler
  training.
- **Where a reader can check.** No document per inspection. The dataset page
  (`https://data.cityofchicago.org/Health-Human-Services/Food-Inspections/4ijn-s7e5`) or a query by ID:
  `https://data.cityofchicago.org/resource/4ijn-s7e5.json?inspection_id={id}`.
- **Unverified.** The legal citations in the prototype (Municipal Code of Chicago § 7-42, 77 Ill. Adm. Code 750).

Checked 2026-11-14: [metadata](https://data.cityofchicago.org/api/views/4ijn-s7e5.json), live queries.

## New York City

- **Source.** Socrata, `data.cityofnewyork.us`, dataset `43nn-pn8j` (DOHMH New York City Restaurant Inspection
  Results). Updated daily.
- **History: three years, open restaurants only.** The description: violations "up to three years prior to the most
  recent inspection for restaurants … in an active status". A restaurant that closes leaves the dataset. Date
  `1900-01-01` means not yet inspected (4,059 rows).
- **Fields.** `camis` (facility ID), `dba`, `boro`, `building`, `street`, `zipcode`, `cuisine_description`,
  `inspection_date`, `action`, `violation_code`, `violation_description`, `critical_flag`, `score`, `grade`,
  `grade_date`, `inspection_type`, `latitude`, `longitude`. One row per violation.
- **Inspector's words: no.** `violation_description` is the standard text for the code.
- **Grades.** Score 0–13 = A, 14–27 = B, 28+ = C. `Z` = grade pending, `P` = grade pending on re-opening, `N` = not
  yet graded. Many rows have no grade.
- **Vermin codes (since mid-2022).** `04K` rats, `04L` mice, `04M` live roaches, `04N` filth flies (house, blow,
  bottle, flesh) and food/refuse/sewage-associated flies (fruit, drain, phorid), `04O` live animals. **Codes changed
  meaning over time:** before about 2011, `04M` meant mice and `04N` meant roaches, and `04K` once meant a missing
  thermometer. Match on code and description, or only use rows from July 2022 on.
- **Where a reader can check.** The city's lookup, `https://a816-health.nyc.gov/ABCEatsRestaurants/` (search by
  name). No per-inspection document.
- **Unverified.** Point values per violation (the prototype said 5 for each vermin code, 7 for holding temperatures,
  10 for sewage); how long grades stay pending.

Checked 2026-11-14: [metadata](https://data.cityofnewyork.us/api/views/43nn-pn8j.json), live queries.

## New York State (outside NYC)

- **Source.** Socrata, `health.data.ny.gov`, dataset `2hcc-shji` (Food Service Establishment Inspections: Beginning
  2005, ACTIVE). Closed facilities are in `aaxz-j6pj` (INACTIVE). Last-inspection-only views: `cnih-y5dw`, map
  `w3v8-k4d4`. The prototype's `cnih-cnpy` no longer exists.
- **Freshness.** Rows updated Nov 8, newest inspection Nov 6, 2026: about weekly.
- **Coverage.** Rows come from county health departments and state district offices. Erie, Suffolk and NYC do not
  appear; they run their own programs.
- **Fields.** `facility`, `address`, `date_of_inspection`, `violation_item`, `violation_description`,
  `critical_violation`, `total_critical_violations`, `inspection_type`, `inspection_comments`,
  `local_health_department`, `nys_health_operation_id`, `permitted_d_b_a`, `permitted_corp_name`, `latitude`,
  `longitude`. One row per violation.
- **Inspector's words: yes,** in `inspection_comments` (e.g. "Hot/cold holding within acceptable ranges…").
- **Watch for** a minimum date of year 0002: filter impossible dates.
- **Unverified.** Grading (NY State does not appear to grade); which item numbers are pests.

Checked 2026-11-14: [metadata](https://health.data.ny.gov/api/views/2hcc-shji.json), Socrata catalog search.

## King County / Seattle

- **Source.** Socrata, `data.kingcounty.gov`, dataset `r878-4sxa` (Food Establishment Inspection Data). Updated
  daily (Nov 14; newest inspection Nov 12, 2026).
- **History.** 2021 on (111,611 rows).
- **Fields.** `name`, `program_identifier`, `business_id`, `inspection_serial_num`, `inspection_date`,
  `inspection_type`, `inspection_score`, `inspection_result`, `inspection_closed_business`, `violation_type`,
  `violation_description`, `violation_points`, `grade`, `risk_category`. One row per violation.
- **Inspector's words: no.** Standard descriptions.
- **Ratings.** `grade`: Excellent, Good, Okay, Needs To Improve, Not Rated, Rating Not Available. Violations are
  `RED` or `BLUE` with points.
- **Pest code.** "3200 - Insects, rodents, animals not present; entrance controlled", BLUE, 5 points.

Checked 2026-11-14: [metadata](https://data.kingcounty.gov/api/views/r878-4sxa.json), live queries.

## San Francisco

- **Source.** Socrata, `data.sf.gov` (`data.sfgov.org` redirects), dataset `tvy3-wexg` (Health Inspection Scores,
  2024-Present). Earlier years: `5tti-66ds` (2020–2023), `pyih-qa8i` (2016–2019). The description says monthly
  updates, but the newest real inspection is Nov 13, 2026. One row is dated 2031-05-16.
- **Fields.** `inspection_date`, `inspector`, `permit_number`, `dba`, `street_address`, `inspection_type`,
  `facility_rating_status`, `violation_count`, `violation_codes`, `inspection_notes`, `suspension_notes`.
- **Inspector's words: no.** `inspection_notes` and `suspension_notes` are empty in every row.
  `violation_codes` lists California Retail Food Code sections each followed by the standard correction text.
- **Results.** `facility_rating_status`: Pass, Conditional Pass, Closure (the city's green, yellow and red placards).
- **Pest code.** CalCode 114259.1 appears in 5,190 rows.
- **Where a reader can check.** DataSF links the city's lookup on MyHealthDepartment:
  `https://inspections.myhealthdepartment.com/san-francisco`.

Checked 2026-11-14: [metadata](https://data.sf.gov/api/views/tvy3-wexg.json), live queries.

## Austin

- **Source.** Socrata, `data.austintexas.gov`, dataset `ecmv-9xxi` (Food Establishment Inspection Scores), Austin
  Public Health.
- **Freshness: about five weeks behind.** On Nov 14 the newest inspection was Oct 10, 2026 (rows loaded Nov 1). The
  prototype's "weekly, 3 days" was wrong.
- **History: three years.** The description says "performed within the last 3 years"; the oldest row is
  Nov 2, 2023. Older inspections drop off.
- **Fields.** `restaurant_name`, `facility_id`, `address`, `zip_code`, `inspection_date`, `inspectionid`, `score`,
  `process_description` (inspection type), `inspectionscorecategory`, `lat`, `lng`.
- **Inspector's words: no.** No violations at all, only the score.
- **Scores.** 100-point scale; `inspectionscorecategory` is "90+ (Green)", "70-89 (Yellow)", " Under 70 (Red)"
  (leading space in the data).
- **Unverified.** The prototype's claim that report PDFs with itemized violations are on a separate city portal; its
  Texas Food Establishment Rules (25 TAC chapter 228) section numbers.

Checked 2026-11-14: [metadata](https://data.austintexas.gov/api/views/ecmv-9xxi.json), live queries.

## Dallas

- **Stopped.** The dataset is now `dri5-wcct` on `www.dallasopendata.com`, "Restaurant and Food Establishment
  Inspections (October 2016 to January 2024)", last updated March 2024. The prototype's `vdbe-q52c` returns 404. No
  current Dallas source was found.

Checked 2026-11-14: Socrata catalog search on `www.dallasopendata.com`.

## Las Vegas / Southern Nevada Health District

- **Source.** ArcGIS feature layer, not Socrata:
  `https://services1.arcgis.com/F1v0ufATbBQScMtY/arcgis/rest/services/Restaurant_Inspections_Open_Data/FeatureServer/0`.
- **Stopped in 2024.** 346,913 rows from 2000 to June 2, 2024. The layer reports an edit on Nov 9, 2026, but no
  newer inspections.
- **Fields.** `Permit_Number`, `Restaurant_Name`, `Location_Name`, `Address`, `Inspection_Date` (text),
  `Inspection_Type`, `Inspection_Demerits`, `Inspection_Grade`, `Inspection_Result`, `Violations`, `Current_Grade`,
  `Current_Demerits`.
- **Inspector's words: no.** `Violations` is codes joined by `|` (e.g. `206|211|2930`).
- **Grades.** A, B, C from demerits **(thresholds unverified)**.

Checked 2026-11-14: layer metadata and queries.

## MyHealthDepartment (Oregon, Multnomah County, Orange County, Virginia, Tennessee)

A hosted inspection portal used by many health departments, one path each:
`https://inspections.myhealthdepartment.com/{path}`. The site returned HTTP 403 to scripted requests on 2026-11-14,
pages and API alike, so nothing below about the API is confirmed. The prototype's adapter POSTed
`{"task": "searchInspections", "data": {"path": …, "start": 0, "count": 50, "filters": {"date": "YYYY-MM-DD to
YYYY-MM-DD"}}}` to the site root and read `inspectionID`, `establishmentName`, `inspectionDate`, `score`, `status`,
`address` **(all unverified)**. Expect to need a browser, or to ask the health department for an export.

### Oregon and Multnomah County

- **Paths.** `oregon` (a statewide page linking county portals) and `multco-eh` (Multnomah County). Both are linked
  by public pages. The prototype's `or-washington-county` and `or-clackamas-county` are **unverified**; Lane County's
  is `or-lane-county`.
- **14-day delay.** The statewide portal says every inspection is posted 14 days after it happens. This is the
  portal's stated policy; no statute requiring it was found.
- **Scores.** 100 points minus 5 per priority violation and 3 per priority foundation violation; core violations cost
  nothing. Repeat violations double. Below 70 fails; a second score under 70 within 30 days means closure. The rules
  are OAR 333-157-0020 and 0030. The prototype said core costs 1 point and cited OAR 333-150; both corrected here.

Checked 2026-11-14: [Oregon portal](https://inspections.myhealthdepartment.com/oregon) (via search index; direct
fetch blocked), [OAR 333-157-0020](https://oregon.public.law/rules/oar_333-157-0020),
[OAR 333-157-0030](https://oregon.public.law/rules/oar_333-157-0030).

### Orange County, California

- **Path.** `orange-county`, titled "Orange County Health Care Agency – Environmental Health Division". The county
  also keeps a two-year search at ochealthinfo.com.
- **Placards: unverified.** The prototype said green, yellow and red (Pass, Conditional Pass, Closed). That is
  Sacramento's and San Francisco's scheme. Orange County's grand jury proposed colours, but no page confirms the
  county adopted them.
- **Vermin.** California Retail Food Code § 114259.1 (also in San Francisco's data).

Checked 2026-11-14: search index for the portal; [OCHCA retail food](https://www.ochealthinfo.com/food/retail).

### Virginia and Tennessee

- **Virginia.** The Virginia Department of Health says its inspections are on MyHealthDepartment
  ([VDH](https://www.vdh.virginia.gov/lord-fairfax/permitted-facility-inspections/)). The path `virginia` is
  **unverified**.
- **Tennessee.** Path `tennessee`, confirmed only by a third-party site **(unverified on a state page)**.

## Directory leads, not checked

From the prototype's nationwide directory, minus entries found wrong. Platform and cadence are the prototype's
claims; none of these was opened on 2026-11-14.

| Where | Agency and URL (unverified) | Platform claimed |
|---|---|---|
| Kansas City, MO | `kcmo.gov` restaurant inspection results | Not on Socrata: `data.kcmo.org` has only a 2017 food-permit list (checked) |
| Minneapolis | Health inspection lookup dashboard, `minneapolismn.gov` | Power BI; not Socrata (checked: not in the catalog) |
| Detroit | `data.detroitmi.gov` restaurant inspections | ArcGIS Hub |
| San Diego County | `sdfoodinfo.org` | ArcGIS |
| Los Angeles County | `ehservices.publichealth.lacounty.gov/ezsearch` | Search form |
| Maricopa County | `envapp.maricopa.gov/EnvironmentalHealth/FoodInspections` | Custom |
| Pima County | `healthinspect.pima.gov/Portal/` | EnvisionConnect |
| Anchorage | `anchorageonline.envisionconnect.com` | EnvisionConnect |
| DC | `dc.healthinspections.us` | HealthSpace |
| Illinois (outside Chicago), Iowa, South Dakota, Vermont | `{state}.safefoodinspection.com` | HealthSpace / SafeFoodInspection |
| Rhode Island | `ri.healthinspections.us` | HealthSpace |
| North Carolina (Wake, Mecklenburg) | `public.cdpehs.com` | CDPEHS |
| North Dakota, Arkansas | `PublicInspectionSearch.aspx` forms | ASP.NET form |
| Wisconsin | `healthspace.com/Clients/WI/State` | HealthSpace |
| Florida | DBPR license search, `myfloridalicense.com` | State database |
| Missouri, Joplin | MyHealthDepartment `jhd` | MyHealthDepartment |
| Delaware | `data.delaware.gov`, dataset `384s-wygj` (Food Establishment Inspection Violations) | Socrata (found in the catalog, not opened) |
| Montgomery County, MD | `data.montgomerycountymd.gov`, dataset `5pue-gfbe` (Food Inspection) | Socrata (found in the catalog, not opened) |

The prototype's HealthSpace notes (ASP.NET forms needing `__VIEWSTATE`, `__EVENTVALIDATION` and a session cookie)
are general, not checked against any one site.
