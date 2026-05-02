# Scoring Model

Last reviewed: 2026-05-02

The engine uses deterministic scoring only. LLMs may summarize already-computed facts later, but
they must not invent measurements, counts, legal status, or scores.

## Status Bands

```text
85-100  excellent
70-84   good
40-69   fair
0-39    poor
```

Legal overrides can force `restricted`, `closed`, or `unknown`.

## Legal Overrides

```text
if active_closure:
  overall_score = 0
  overall_status = closed
  legal_status = closed

else if active_restriction:
  overall_score = min(computed_score, 45)
  overall_status = restricted
  legal_status = restricted
```

Emergency orders are evaluated against `effective_date` and `expires_date` when those dates are
available. Unknown or PDF-only emergency orders create manual-review warnings and lower legal
confidence.

## Environmental Score

```text
environmental_score = base_score
environmental_score += water_temperature_modifier
environmental_score += flow_percentile_modifier
environmental_score += gage_trend_modifier
environmental_score += rain_modifier
environmental_score += wind_modifier
environmental_score += barometric_modifier
environmental_score += flood_alert_modifier
```

| Signal | Rule | Modifier |
|---|---:|---:|
| Water temperature 45-58 F | salmonid comfort band | +10 |
| Water temperature 59-62 F | warm | -6 |
| Water temperature >62 F | fish stress | -16 |
| Water temperature <38 F | slow movement | -8 |
| Flow percentile 35-75 | normal fishable range | +8 |
| Flow percentile 85-94 | high flow/access penalty | -12 |
| Flow percentile >=95 | dangerous high flow | -25 |
| Flow percentile <15 | very low flow/access risk | -10 |
| Gage trend abs <=0.25 ft | stable | +4 |
| Gage trend >0.75 ft | rapid rise | -8 |
| Rain <=0.15 in/24h | dry/stable weather | +3 |
| Rain >=0.75 in/24h | rain/clarity risk | -8 |
| Wind <=10 mph | easier boating/casting | +2 |
| Wind >=20 mph | boating/casting penalty | -6 |
| Flood watch | safety penalty | -10 |
| Flood warning | safety penalty | -18 |

## Weighted Output

```text
overall_score =
  round(environmental_score * 0.50
      + selected_location_score * 0.25
      + selected_species_score * 0.25)
```

All scores clamp to 0-100.

## Location Fit

Current deterministic outputs include:

- `bank_fishing_score`
- `boat_fishing_score`
- reach-level `condition_score`
- water provenance and trend

Lower river locations receive tide context. High flow reduces reach scores because access, clarity,
and boat safety degrade differently by segment.

## Species Fit

The report includes supported species scores only when official data support them. Unsupported
species are emitted as `unknown` with an explanation. The current supported numeric species signal is
sockeye from official ADF&G count records; Chinook, coho, rainbow trout, and Dolly Varden remain
unknown unless future adapters provide explicit official data.

## Confidence

Confidence starts from `ScoreInput.confidence`, then rises to at least `0.72` when source-health
freshness exists. It is reduced by:

- `0.08` for each stale source
- `0.10` for each missing required source
- additional report-builder penalties for missing baseline regulations

Freshness thresholds:

| Source | Fresh if checked within |
|---|---:|
| USGS | 6 hours |
| USGS statistics | 168 hours |
| NWS | 3 hours |
| ADF&G emergency orders | 24 hours |
| ADF&G fish counts | 36 hours |
| NOAA tides | 24 hours |

## Explanation Model

Every score result carries:

- `score_delta_reason`
- `contributing_factors`
- `limiting_factors`
- `confidence_explanation`
- `legal_explanation`
- `recommended_user_action`

These are deterministic strings assembled from scoring inputs and source-health state.

## Future Improvements

- Validate additional Kenai USGS sites and map them per river segment.
- Add explicit turbidity scoring once live turbidity is available for a validated site.
- Split Russian River and Kenai late-run sockeye into separate species/location fit signals.
- Add ADF&G fishing report parser for official narrative explanations.
- Add DNR and City of Kenai access status as warnings, not score drivers, until stable.
