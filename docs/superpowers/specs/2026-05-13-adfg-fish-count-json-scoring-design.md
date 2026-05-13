# ADF&G Fish Count JSON Scoring Design

Date: 2026-05-13

## Goal

Use official ADF&G Fish Counts JSON export records as biological scoring inputs for every species and location the records support. The existing adapter already fetches `ADFG=export.JSON` URLs and normalizes the ADF&G `COLUMNS`/`DATA` payload shape. This design updates the engine equations so those normalized records influence more than Kenai sockeye.

## Current State

`src/kenai_engine/sources/adfg_fish_counts.py` builds JSON export URLs and parses records into `FishCount` fields including `species`, `location`, `count`, `observation_date`, `count_location_id`, `species_id`, and optional daily/cumulative values.

`src/kenai_engine/report_builder.py` currently reduces fish-count records mostly to Kenai sockeye:

- Overall `ScoreInput` uses a Kenai sockeye three-day average and trend.
- Location relevance maps Russian River separately, but most other count use is limited to Kenai sockeye and lower-river locations.
- Species scoring reports a supported species when count records exist, but the scoring equation itself only uses sockeye count magnitude plus a generic trend.

## Data Model

Add an internal derived signal layer, not a new stored record type.

`FishCountSignal` should be a small internal structure with:

- `species_key`: normalized species key such as `sockeye`, `chinook`, or `coho`
- `location_key`: normalized count-location bucket such as `kenai`, `russian`, or `kasilof`
- `recent_avg`: average of the newest three count records in the group
- `latest_count`: newest count value
- `trend`: `rising`, `steady`, `falling`, or `unknown`
- `latest_observation_date`: newest ADF&G count date
- `count_location_id` and `species_id` when available

This signal is derived from the normalized `FishCount` list during report construction. It should stay deterministic and offline-safe.

## Scoring Behavior

Species scores should use matching fish-count signals for all supported species:

- Sockeye keeps high-volume thresholds, but uses the matching species signal rather than scanning only Kenai records.
- Chinook and coho use lower-volume, trend-sensitive thresholds so they are not scored as poor simply because normal counts are lower than sockeye counts.
- Unknown or unsupported species keep the current unknown score behavior.

Location scores should use fish-count signals that match the report location:

- Russian River locations use Russian River sockeye signals.
- Soldotna, lower Kenai, and Kenai mouth locations use Kenai River signals.
- Other locations receive fish-count influence only when an explicit mapper associates the location with a count source.

Overall score should receive only a modest biological adjustment. Fish counts are a strong activity signal, but they should not override legal status, hydrology, weather, tide, or source-health constraints.

Missing fish-count data should reduce confidence through source health, not create a zero-count penalty. A real ADF&G zero count remains valid data and may lower the biological signal for that species/location.

## Equation Shape

Keep the current scoring architecture, but replace the sockeye-only fish-count inputs with signal-aware inputs:

- Derive per-species/per-location signals in `report_builder`.
- Use the target location and target species to choose the best signal for the overall score input.
- Update species score construction so each species pulls its own best signal.
- Update location component scoring so relevant fish-count signals can nudge location scores.

Initial threshold shape:

- Sockeye: high positive at strong recent averages, neutral at moderate counts, negative only when current counts are genuinely low for an active run.
- Chinook/coho: prioritize trend, recency, and nonzero activity over large absolute thresholds.
- Falling trends apply a smaller penalty than stale or missing source-health penalties.

Exact constants should be conservative and covered by unit tests.

## Error Handling

- Malformed JSON parsing continues to mark ADF&G fish counts as degraded through the existing normalization failure path.
- Empty JSON data for an active source is valid but should produce no signal.
- Count records with missing dates, species, locations, or count values are skipped.
- Stale source health affects confidence and report warnings through existing source-health handling.

## Testing

Add focused tests for:

- Signal derivation from multiple ADF&G JSON species and count locations.
- Sockeye, Chinook, and coho species scores changing from their own signals.
- Russian River and lower Kenai locations selecting different count signals.
- Missing active fish-count records reducing confidence but not forcing poor scores.
- Real zero counts remaining valid data.
- Report provenance carrying ADF&G `count_location_id`, observation date, and role for matched locations.

## Out of Scope

- Scraping Oracle Analytics embedded dashboards.
- Adding new persisted database tables.
- Calibrating a full historical biological model by run, species, and day-of-year.
- Changing legal/regulatory override behavior.
