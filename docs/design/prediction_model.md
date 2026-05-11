# Deterministic Production Prediction Model

The production engine uses a transparent deterministic model. It does not ask an LLM to invent scores. Every score is a weighted combination of known inputs with legal overrides applied first.

## Outputs

- `overall_score`: 0-100
- `location_scores`: Cooper Landing/upper river, middle Kenai, Soldotna, lower Kenai
- `species_scores`: sockeye, Chinook/king, coho, rainbow trout, Dolly Varden
- `confidence`: 0-1
- `legal_status`: open, restricted, or closed
- `source_freshness_status`: fresh, stale, or missing
- `reasons`: short deterministic explanations

## Hard Overrides

1. If ADF&G emergency orders or regulations indicate a closure for the selected species/location/date, return `overall_score = 0`, `overall_status = closed`, and `legal_status = closed`.
2. If an active restriction applies, cap `overall_score` at 45 and return `overall_status = restricted`.
3. If a flood warning or dangerous flow is active, keep the fishability score but force `overall_status = caution`.
4. If legal data is missing or stale, never report high confidence.

## Base Formula

```
environmental_score = base_score
environmental_score += water_temperature_modifier
environmental_score += flow_percentile_modifier
environmental_score += gage_trend_modifier
environmental_score += rain_modifier
environmental_score += wind_modifier
environmental_score += barometric_modifier
environmental_score += flood_alert_modifier

selected_location_score = location_scores[selected_location]
selected_species_score = species_scores[selected_species]

overall_score =
  round(environmental_score * 0.50
      + selected_location_score * 0.25
      + selected_species_score * 0.25)
```

All intermediate scores are clamped to 0-100.

## Production Weights and Rules

| Signal | Rule | Modifier |
|---|---:|---:|
| Water temp 45-58 F | Primary salmonid comfort band | +10 |
| Water temp 59-62 F | Warm | -6 |
| Water temp >62 F | Stress/catchability penalty | -16 |
| Water temp <38 F | Cold movement penalty | -8 |
| Flow percentile 35-75 | Normal fishable range | +8 |
| Flow percentile 85-94 | High flow | -12 |
| Flow percentile >=95 | Dangerous high flow | -25 |
| Flow percentile <15 | Very low flow/access risk | -10 |
| 24h stage trend abs <=0.25 ft | Stable stage | +4 |
| 24h stage trend >0.75 ft | Rapid rise | -8 |
| Rain <=0.15 in/24h | Minimal rain | +3 |
| Rain >=0.75 in/24h | Heavy rain/clarity proxy | -8 |
| Wind <=10 mph | Fishable/castable | +2 |
| Wind >=20 mph | Boating/casting penalty | -6 |
| Barometric trend steady | Weak positive | +2 |
| Barometric trend falling | Weak negative | -3 |
| Flood watch | Safety penalty | -10 |
| Flood warning | Strong safety penalty | -18 |

## Location Logic

Locations use the environmental score as the base, then apply reach-specific modifiers.

- Cooper Landing / upper river: use USGS Cooper Landing, Russian River status/counts, drift-only constraints, cold-water safety, and upper-river access.
- Middle Kenai: use Soldotna/USGS trend, Killey River turbidity inference, Skilak influence, boat access.
- Soldotna: use Soldotna gauge, ADF&G RM19 counts, bank/boat access and crowd proxies.
- Lower Kenai / tide-influenced: use Soldotna gauge plus NOAA tides, City Dock status/cameras, and dipnet/crowd windows.

Current production code applies:

```
if tide_stage == incoming: lower_kenai += 8
if tide_stage == outgoing: lower_kenai -= 5
if flow_percentile >= 90:
  upper_kenai -= 8
  middle_kenai -= 12
  soldotna -= 10
  lower_kenai -= 8
```

## Species Logic

Sockeye:

- Use ADF&G RM19 3-day average and trend.
- `fish_count_3day_avg >= 30,000`: +15
- `>= 10,000`: +8
- `< 2,000`: -10
- Rising trend: +6; falling trend: -6
- Russian River counts should become a separate upper-river/Russian modifier in the first adapter pass.

Chinook/king:

- Legal gate first. If closed, score 0.
- If open in a future season, use lower-river tide, king sonar/ADF&G reports, temperature, and conservative flow/access rules.

Coho:

- Use late-summer seasonal prior, incoming tide in lower river, cooling/rain cues, and ADF&G reports.
- Current production code gives a small rising-count/tide boost but marks confidence lower if no direct coho source exists.

Rainbow trout and Dolly Varden:

- Use legal season, water temperature, flow/clarity, and salmon-spawn/egg availability.
- Penalize warm water; future adapter should add spawning-stage inputs from sockeye timing and reports.

## Confidence Rules

Start with `ScoreInput.confidence`, default `0.35`. If source freshness data exists, raise the baseline to at least `0.72`, then subtract:

- `0.08` for each stale source
- `0.10` for each missing required source

Freshness thresholds:

| Source | Fresh if checked within |
|---|---:|
| USGS | 6 hours |
| NWS | 3 hours |
| ADF&G emergency orders | 24 hours |
| ADF&G fish counts | 36 hours |
| NOAA tides | 24 hours |

## First Self-Review

Weak assumptions in the first model:

- It treats clarity as inferred because no live Kenai turbidity feed was found.
- It uses generic temperature bands rather than validated species/reach curves.
- It has only basic season/run logic until adapters provide historical day-of-year percentiles.
- Barometric pressure is included but intentionally weak because evidence is not strong enough for larger weight.
- Crowd pressure is not in code yet because reliable live data is not available.

Improvement: keep barometric/crowd weights small, hard-gate legal status, and use source freshness to prevent false precision.

## Second Self-Review

The improved method is safer but can still mislead if RM19 counts are applied too far upstream or outside late-run sockeye. To reduce that risk:

- Treat Russian River counts separately from lower-river sockeye counts.
- Never boost Chinook when a closure exists.
- Require source provenance in adapter records.
- Display reasons and freshness next to every score.
- Keep manual/social reports out of automated scoring until reviewed.

## Production Source Scope

The production engine ships with official machine-readable sources only:

- USGS Cooper Landing/Soldotna
- ADF&G fish counts
- ADF&G EOs
- NWS alerts/forecast
- NOAA tides

Manual-review sources may appear as notes, not automated score drivers. Future advanced ideas include camera-based crowd/clarity estimates, historical catch-log calibration, NOAA/NWM forecast blending, and species-specific empirical models.
