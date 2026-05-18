# Source Ingestion Standards

These standards apply to adapters, parsers, raw snapshot storage, normalization,
source-health reporting, and ingestion automation.

## Parser Resilience

- Parsers must treat source structure changes as expected production events.
- Prefer structured APIs and exports over scraped HTML or PDFs when official
  sources provide them.
- Scraped and PDF-derived records must include parser warnings when required
  fields, dates, species, locations, or legal classifications cannot be validated.
- Parser tests should use small fixtures that represent successful, stale,
  partial, empty, malformed, and source-structure-changed responses.
- A parser must not silently drop records that look relevant but cannot be fully
  classified. Emit partial records with warnings or fail explicitly.
- Parser outputs should expose coverage counts when practical: records seen,
  parsed, emitted, skipped, failed, and emitted with warnings. Skipped and failed
  records need reason buckets that support maintenance.

## Retry Handling

- Retries should be bounded, observable, and source-specific.
- Retry transient network failures, rate limits, and temporary server failures
  when doing so will not duplicate side effects.
- Do not retry deterministic parser failures as if they were network failures.
- Preserve the final failure reason, retry count, and timestamp in diagnostics or
  source-health output when a source affects report confidence.
- Repeated retry exhaustion should be distinguishable from first-time transient
  failure so operations can detect persistent source degradation.

## Source Validation

- Every adapter should validate source identity, expected content type, minimum
  required fields, timestamp plausibility, and record count plausibility.
- Official legal and safety sources require stricter validation than convenience
  or context sources.
- Records should retain provenance: source id, source URL, fetched timestamp, raw
  snapshot identifier when available, and parser version or parser path when
  practical.
- Do not normalize away source uncertainty. Keep manual-review flags,
  classification uncertainty, and parse warnings attached to affected records.

## Stale And Partial Source Handling

- Each source must have a documented freshness threshold based on production
  risk, update cadence, and report impact.
- Stale required sources must reduce confidence and create app-facing source
  health or warning output.
- Missing legal or safety sources must never allow high-confidence unrestricted or
  safe-looking guidance.
- Partial parser success must be visible. If a parser extracts some records but
  cannot classify others, the report should preserve the successful records and
  surface the incomplete coverage.

## Failure Transparency

- Prefer explicit failure states over silent fallback data.
- Fallbacks may use the last successful source snapshot only when the report
  clearly labels the data as stale and lowers confidence.
- Manual-review conditions must be visible in machine-readable report fields, not
  only in logs.
- Parser warnings should be specific enough to support maintenance: source,
  record, missing field, invalid value, ambiguous classification, or unexpected
  structure.

## Redundancy

- Use redundant sources only when their authority and semantics are clear.
- Official sources should remain primary for legal status, fish counts, water
  measurements, weather alerts, and tide predictions.
- Convenience aggregators, commercial reports, guide narratives, cameras, or
  social content may support manual-review context but must not override official
  source-backed scoring without explicit validation rules.
- When redundant sources disagree, preserve the disagreement and favor the source
  with higher authority instead of averaging away conflict.

## Source Health And Observability

- Source-health output should identify status, severity, last success time,
  freshness, last error, affected report surfaces, and whether the source affects
  score or legal status.
- Source-health output should identify publish impact: informational, degraded
  but publishable, publish with critical warning, or block publishing.
- Operational logs should make it possible to answer: which source failed, when
  it last succeeded, what parser path failed, which records were affected, and
  what report fields were downgraded.
- Production automation should validate generated reports after ingestion and
  fail visibly when contract or safety-critical source assumptions are violated.
- Diagnostics should be stable enough for future monitoring automation to detect
  repeated failures, parser drift, stale feeds, and source endpoint changes.

## Operational Readiness

- Legal, safety, water, weather, fish count, tide, and historical context sources
  should have explicit degradation severity and publish behavior.
- Last-known-good fallback must identify the source snapshot used, the age of the
  data, the freshness threshold exceeded, and the report fields affected.
- Repeated source failures should escalate severity after a documented threshold
  rather than appearing as identical one-off failures forever.
- Scheduled publishing failures should be visible in automation logs and should
  not silently leave stale public reports looking current.
- Critical legal or safety source failures should either block publication or
  publish only with explicit critical warnings and reduced confidence, depending
  on the documented source policy.

## Deterministic Normalization

- Normalization should be deterministic for identical raw snapshots.
- Unit conversions, date parsing, location mapping, species mapping, and enum
  mapping must be explicit and tested.
- Normalized records should avoid lossy transformations unless the raw snapshot
  remains available for audit.
- Do not allow parser order, network timing, or incidental dictionary ordering to
  change report semantics.
