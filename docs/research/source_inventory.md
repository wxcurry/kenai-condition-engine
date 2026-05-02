# Kenai Pulse Source Inventory

Last reviewed: 2026-05-02

Access modes: `machine_readable`, `scrape`, `manual_review`, `unsuitable`.

| Source | URL | Category | Access | Freshness | Reliability | Prediction value | MVP priority | Limitations |
|---|---|---|---|---|---|---|---|---|
| USGS NWIS IV | https://waterservices.usgs.gov/nwis/iv/ | river conditions | machine_readable | ~15 minute readings, often hourly transmission | high, provisional | flow, stage, temperature, turbidity, trend | P0 | Some parameters unavailable by site; invalid site/parameter combos can return 404. |
| USGS Water Data OGC latest-continuous | https://api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous | river conditions | machine_readable | near real time | high | future adapter path | P2 | Needs field mapping before replacing NWIS IV. |
| NWS API | https://api.weather.gov | weather/alerts | machine_readable | forecast lifecycle/cache dependent | high | rain, wind, temperature, hazards | P0 | Requires User-Agent; point grid mapping can change. |
| NOAA CO-OPS datagetter predictions | https://api.tidesandcurrents.noaa.gov/api/prod/datagetter | tides | machine_readable | prediction table | high | lower river timing and safety context | P1 | Station choice must stay documented; lower-river only. |
| ADF&G Fish Counts | https://www.adfg.alaska.gov/sf/FishCounts/ | fish counts | scrape | seasonally updated | official, parser-sensitive | run strength and presence | P0 | HTML can change; graphs may require manual review. |
| ADF&G Emergency Orders and Press Releases | https://www.adfg.alaska.gov/sf/EONR/ | legal status | scrape/manual_review | frequently updated | official | closure/restriction/liberalization overrides | P0 | PDF-only orders require manual review. |
| ADF&G Fishing Reports | https://www.adfg.alaska.gov/sf/FishingReports/ | official narrative | scrape | report cadence varies | official narrative | explanation/context | P2 | Narrative should not drive numeric scores without explicit rules. |
| Baseline sport regulations | https://www.adfg.alaska.gov/index.cfm?adfg=fishingSportFishingInfo.scregs | legal baseline | manual_review | annual/seasonal | official when reviewed | legal context and confidence | P0 | JSON config is not legally complete. |
| Alaska DNR KRSMA pages | https://dnr.alaska.gov/parks/aspunits/kenai/krsma.htm | access/boating | scrape | static/occasional | official | boat/access warnings | P2 | No stable machine status feed found. |
| City of Kenai dipnet pages/cameras | https://www.kenai.city/ | lower-river access | scrape/manual_review | seasonal/varies | official local | dipnet, fees, parking, visibility metadata | P2 | Webcam metadata only for MVP; no computer vision. |
| Guide/tackle reports/forums/social | varies | anecdotal | manual_review/unsuitable | variable | mixed | color only | P3 | Do not automate into scores without permission and validation. |
| Academic and hydrology papers | varies | research | manual_review | static | high when peer-reviewed | future model calibration | P3 | Not operational live data. |

## Current MVP Source List

- `usgs`: official NWIS IV JSON for parameters `00060,00065,00010,63680,00095,00300,00400`.
- `usgs_statistics`: official NWIS statistics RDB/JSON for flow percentile context.
- `nws`: official points, forecast, hourly forecast, grid, and alerts data.
- `noaa_tides`: official CO-OPS high/low tide predictions.
- `adfg_fish_counts`: official ADF&G pages parsed from HTML or embedded JSON.
- `adfg_emergency_orders`: official ADF&G EONR HTML/detail pages; PDFs flagged for manual review.
- `baseline_regulations`: local manual-review JSON config.

## Station And Site Policy

Only validated sites belong in default config. A live NWIS IV check on 2026-05-02 showed the
requested `10172640` resolves to Lee Creek near Magna, Utah, so it is not used as an authoritative
Kenai default. Current validated Kenai defaults are:

- `USGS-15258000` / `15258000`: Kenai River at Cooper Landing, AK.
- `USGS-15266010` / `15266010`: Kenai River below Russian River near Cooper Landing, AK.
- `USGS-15266110` / `15266110`: Kenai River below Skilak Lake outlet near Sterling, AK.
- `USGS-15266300` / `15266300`: Kenai River at Soldotna, AK.

Additional sites should be added only after live API validation and documented source-health
behavior for missing parameters.
