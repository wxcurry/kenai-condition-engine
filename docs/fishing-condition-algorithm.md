# Fishing Condition Algorithm

Last reviewed: 2026-05-05

This model is deterministic planning guidance for field fishing conditions. It is
not legal advice, safety authority, or a catch guarantee. Users must check
official ADF&G regulations and emergency orders, USGS/NWS conditions, and local
access information before fishing.

## Inputs

Supported now:

- Hydrology: flow percentile, flow trend, water temperature, turbidity when
  measured, recent rain proxy.
- Tide: incoming, outgoing, slack high/low, tide height delta, time to next high
  or low tide for tide-relevant access points.
- Weather: wind, rain, pressure trend, storm/severe-weather signal.
- Biological and seasonal: user-provided historical sockeye seed timing,
  ADF&G fish-count trend when callers supply it, pulse strength, 7-day average.
- Access: selected access match, tide relevance, stage fit, degraded access
  source flag.
- Data quality: fresh, stale, missing, cached, and malformed source labels.

Deferred:

- Live crowd pressure, guide activity, cameras, parking status, moon/solunar
  periods, and user reports. These need stable source contracts or product
  decisions before they should affect scores.
- Turbidity proxy from rain plus rising flow/stage. The model accepts measured
  turbidity today; inferred clarity should be added with a visible proxy label.
- Android UI rendering. This repository is the Python data engine; Android is a
  consumer of static JSON.

## Model

The pure engine lives in `src/kenai_engine/fishing_conditions.py`.

```text
rawScore =
  0.25 * hydrologyScore +
  0.20 * tideScore +
  0.15 * weatherScore +
  0.20 * seasonalBiologicalScore +
  0.10 * recentActivityScore +
  0.10 * accessScore

finalScore = clamp(round(rawScore * dataQualityMultiplier), 0, 100)
```

Rating bands:

- 0-39: Poor
- 40-69: Fair
- 70-84: Good
- 85-100: Excellent

Confidence is separate from score. Strong condition signals can still produce
low confidence when sources are stale, cached, missing, or malformed.

## Data Freshness

Source quality reduces confidence and can apply a small score multiplier:

- stale: confidence penalty and small score multiplier penalty
- cached: larger confidence penalty; visibly labeled `cached/stale`
- missing: confidence and score multiplier penalty
- malformed: largest confidence and score multiplier penalty

The output includes `dataFreshnessSummary` and structured positive/negative
factors. Cached ADF&G data must not be described as current.

## Historical Sockeye Seed Data

`data/config/historical_sockeye_run_timing.csv` contains user-provided seed
records for 2019-2024 sockeye timing. The loader returns `historical_only=True`
so downstream copy can avoid treating it as live ADF&G data. This seed baseline
supports run phase, timing percentile, pulse strength, and 7-day average until a
validated historical ADF&G export replaces it.

## Examples

High score / high confidence: fresh USGS, NOAA, NWS, and ADF&G sources; normal
flow, favorable temperature, incoming tide at the mouth, and peak sockeye timing.

High score / low confidence: favorable hydrology and tide, but cached ADF&G or
stale USGS source health. Show “Good conditions signal, Low confidence.”

Poor score / high confidence: fresh sources showing high flow, heavy rain, high
wind, or warm water.

Missing data fallback: the engine still returns a score, but confidence drops
and negative factors explain missing tide, weather, hydrology, or biological
inputs.

Cached data fallback: cached/stale sources remain visible in
`dataFreshnessSummary`; official-source reminder stays present.

## Guardrails

- Do not say “safe,” “legal,” “allowed,” “permitted,” “all clear,” or guarantee
  catching fish.
- Use “planning signal,” “conditions signal,” “source check,” and “verify
  official ADF&G” language.
- Emergency-order and regulation interpretation stays in the existing legal
  guardrail layer; this algorithm only describes fishing-condition signals.
