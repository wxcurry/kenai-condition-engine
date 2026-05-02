# API Mapping

Last reviewed: 2026-05-02

## USGS NWIS IV

MVP endpoint:

```text
https://waterservices.usgs.gov/nwis/iv/?format=json&sites={SITE_IDS}&parameterCd=00060,00065,00010,63680,00095,00300,00400&siteStatus=all
```

The adapter also requests a recent window for trend detection. Internally, monitoring IDs normalize
both `15258000` and `USGS-15258000` to:

```json
{
  "monitoring_location_id": "USGS-15258000",
  "nwis_site_id": "15258000"
}
```

Note: a live 2026-05-02 check showed `10172640` resolves to a Utah site, so it is documented as a
rejected candidate rather than a Kenai default.

| Code | Normalized field | Unit | Priority | Use |
|---|---|---|---|---|
| `00060` | `discharge_cfs` | ft3/s | must_have | flow strength, wading/boating safety, fishability |
| `00065` | `gage_height_ft` | ft | must_have | river level, bank access, trend |
| `00010` | `water_temp_c`, `water_temp_f` | degC/degF | must_have | fish activity, salmon movement, trout stress |
| `63680` | `turbidity_fnu` | FNU | high_if_available | water clarity |
| `00095` | `specific_conductance_us_cm` | uS/cm | medium | chemistry/mixing anomalies |
| `00300` | `dissolved_oxygen_mg_l` | mg/L | medium_if_available | fish stress and water quality |
| `00400` | `ph` | standard units | low_medium | water quality anomalies |

Trend classification uses recent observations for `00065`, compares early-window and late-window
medians, and protects against a single noisy latest measurement.

## USGS Water Data OGC

Candidate endpoints:

- https://api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous
- https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous

These remain documented candidates. NWIS IV stays the MVP adapter because the current code and tests
already parse WaterML JSON and support parameter-code mapping.

## National Weather Service

Workflow:

1. `GET https://api.weather.gov/points/{lat},{lon}`
2. Read `properties.forecast`, `properties.forecastHourly`, and `properties.forecastGridData`.
3. Fetch returned forecast URLs.
4. Fetch `GET https://api.weather.gov/alerts/active?point={lat},{lon}`.

Normalized weather fields:

- `temperature_f`
- `wind_mph`
- `wind_direction`
- `short_forecast`
- `precipitation_probability`
- `detailed_forecast`
- `recent_rain_inches_24h`

Grid precipitation is converted from millimeters to inches. Grid wind speed is converted from km/h
to mph. Alerts map NWS severity `Extreme`/`Severe` to `warning`, `Moderate` to `watch`, and others
to `info`.

## NOAA CO-OPS

Endpoint:

```text
https://api.tidesandcurrents.noaa.gov/api/prod/datagetter
```

Parameters:

- `product=predictions`
- `station={NOAA_TIDE_STATION_ID}`
- `datum=MLLW`
- `time_zone=gmt`
- `units=english`
- `interval=hilo`
- `format=json`

The current default is station `9455742`. It is treated as lower-river/Cook Inlet timing context,
not an upper-river signal.

## ADF&G Fish Counts

Primary configured pages:

- Kenai River late-run sockeye: `COUNTLOCATIONID=40`, `SPECIESID=420`
- Russian River early/late sockeye candidate pages are fetched as configured constants.

Parser paths:

- HTML tables with species/location/count/date columns.
- ADF&G display text rows.
- Embedded JSON and `COLUMNS`/`DATA` JSON-like exports.

The engine stores raw snapshots and never fabricates counts. If data cannot be extracted reliably,
future parser-health records should mark `parser_degraded` or `manual_review_required`.

## ADF&G Emergency Orders

Endpoint:

```text
https://www.adfg.alaska.gov/sf/EONR/
```

Parser fields:

- title
- URL
- summary
- effective date
- expiration date
- status: closure, restriction, open/liberalization, unknown
- content type: html/pdf/unknown
- manual-review flag

PDF-only orders preserve the PDF URL and require manual review. Active closures and restrictions
override fishing quality.
