# Source Adapter Plan

Build adapters in order of legality and predictive value. Avoid paid APIs, secret keys, and social scraping.

## Build First

| Order | Adapter | Source URLs | Data | Access | Why first |
|---:|---|---|---|---|---|
| 1 | `adfg_emergency_orders` | https://www.adfg.alaska.gov/sf/EONR/ and https://newsrelease.adfg.alaska.gov/sf/EONR/index.cfm?ADFG=area.list&AreaID=5&Year=2026 | Closures, restrictions, liberalizations, effective/expiration dates, species/location text | scrape HTML/PDF links | Legal hard gate; stale data is the highest-risk failure |
| 2 | `usgs_kenai_gages` | https://api.waterdata.usgs.gov/, sites `15258000`, `15266300` | Flow, gage height, water temperature, historical statistics | machine-readable | Core environmental scoring |
| 3 | `adfg_fish_counts` | https://www.adfg.alaska.gov/sf/FishCounts/index.cfm?ADFG=main.displayResults&COUNTLOCATIONID=40&SPECIESID=420 and Russian River count URLs | Daily/cumulative counts, JSON/Excel export | machine-readable/export plus scrape fallback | Core run timing and fish-movement signal |
| 4 | `nws_weather_alerts` | https://weather-gov.github.io/api/general-faqs | Alerts, precipitation forecast, wind, weather observations | machine-readable | Safety and catchability modifiers |
| 5 | `noaa_tides` | https://api.tidesandcurrents.noaa.gov/api/prod/ and https://tidesandcurrents.noaa.gov/tide_predictions | Tide predictions and station metadata | machine-readable | Lower Kenai/dipnet timing |
| 6 | `adfg_regulations_static` | https://www.adfg.alaska.gov/static/regulations/fishregulations/PDFs/southcentral/2026sc_sfregs_kenai_river.pdf | Static annual rules | manual-review/PDF parse | Baseline when no EO applies |

## Build Later

| Adapter | Source URLs | Access | Use | Reason to wait |
|---|---|---|---|---|
| `city_kenai_access` | https://www.kenai.city/dipnet, https://www.kenai.city/dipnet/page/city-dock | scrape/manual | Dipnet season, dock services, lower launch status | Seasonal pages and tables need parser design |
| `city_kenai_cameras` | https://www.kenai.city/dipnet/page/dipnet-cameras, https://stream.kenai.city/ | manual-review/future CV | Visual crowd/clarity/access confirmation | Video/image URLs can change; no need for MVP scoring |
| `dnr_krsma_access` | https://dnr.alaska.gov/parks/aspunits/kenai/krsma.htm | scrape/manual | Reach rules, motor restrictions, static access context | Mostly static; can be curated |
| `recreation_russian_river` | https://www.recreation.gov/camping/campgrounds/232213 | scrape/manual | Russian River access closures/reservations | Useful for access, not core scoring |
| `nwps_flood_forecast` | https://water.noaa.gov/about/api | machine-readable | Flood stages, forecasts, impacts | Needs identifier mapping and more model work |
| `kpb_gis` | https://www.kpb.us/local-governance-and-permitting/borough-information/reference-library/kpb-maps | ArcGIS REST | Access maps, floodplain, parcels | Spatial enrichment after core pipeline |

## Manual-Review Only

| Source | URL | Why manual |
|---|---|---|
| Guide reports | https://kenaiflyfish.com/, https://marlowsonthekenai.com/blog/kenai-river-fishing-report-2026/ | Commercial, irregular, useful context but must be verified |
| KRSA Fish Central | https://krsa.com/fish-central/kenai/ | Aggregator/advocacy source; verify against ADF&G |
| AlaskaFishCounts | https://alaskafishcounts.com/ | Convenience layer but must validate against official ADF&G |
| Kenai Fishing dashboard | https://app.kenai-fishing.com/ | Interesting UX, but values need validation before trust |

## Excluded From MVP Automation

| Source | Reason |
|---|---|
| Facebook groups/posts | Login/social scraping risk and low repeatability |
| Forum trip reports | Anecdotal, stale, and not operational |
| Paid weather/fishing APIs | User explicitly requested no paid APIs unless optional; official free APIs cover MVP |

## Adapter Contract

Each adapter should persist:

- `source_name`
- `source_url`
- `fetched_at`
- raw payload
- normalized records with `observed_at` or `effective_date`
- freshness status
- parser warnings

Tests should use small fixtures and never hardcode fragile live values. Live integration checks can assert schema and source freshness without asserting exact counts, temperatures, or tides.
