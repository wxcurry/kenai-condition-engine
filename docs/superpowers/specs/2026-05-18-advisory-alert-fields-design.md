# Advisory Alert Fields Design

## Goal

Add detailed advisory explanation fields to each report alert without adding a new top-level
report section.

## Approved Shape

The report keeps the existing top-level `alerts` array. Each alert gains two string fields:

- `advisory_explanation`: a plain-language explanation of what the advisory means.
- `fishing_impact`: a plain-language explanation of how the advisory reason affects someone fishing.

Existing fields remain unchanged: `title`, `severity`, `summary`, and `source`.

## Behavior

Report generation should populate the new fields for normalized alerts. Source adapters may omit the
fields when parsing raw source data; the report builder should enrich missing values deterministically
from the alert title, severity, summary, and source.

Known advisory types should get specific explanations:

- Flood watches and warnings explain potential or active high-water risk and fishing impacts such as
  unsafe wading, reduced bank access, harder boat control, changed holding water, and lower clarity.
- Manual-review ADF&G order alerts explain that the official order could not be confidently parsed and
  that anglers must verify the legal details before relying on the report.
- ADF&G fishing-report alerts explain that they are official narrative context, not a legal or safety
  override.

Other alerts should receive a generic advisory explanation based on the title and summary.

## Compatibility

This is a schema-compatible additive change for consumers that ignore unknown fields. The schema
version stays `1.0.0` unless Android requires strict generated models that reject added alert fields.

## Tests

Add focused report-builder tests that prove:

- Alert JSON includes `advisory_explanation` and `fishing_impact`.
- Flood advisories receive fishing-specific impact copy.
- Manual-review emergency-order alerts receive legal-verification impact copy.
