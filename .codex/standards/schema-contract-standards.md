# Schema Contract Standards

These standards protect the structured reports emitted by the Kenai Conditions
Engine and consumed by Kenai Pulse and any future clients.

## Versioning Rules

- Every app-facing report must include `schema_version`.
- Use semantic versioning for report contracts:
  - Patch changes preserve all existing fields, enum values, and semantics.
  - Minor changes may add optional fields or enum values that clients can ignore.
  - Major changes may remove fields, change requiredness, rename fields, or alter
    existing semantics.
- A breaking change requires a version transition plan, validation updates,
  fixture updates, client communication, and a compatibility window when
  practical.
- Deprecated fields must remain populated and semantically stable until the
  declared compatibility window ends. Deprecation should add a replacement field
  before removing or changing the old field.
- Do not use schema version bumps to hide ambiguity. The intended client behavior
  for old and new versions must be explicit.

## Required And Optional Fields

- Required fields must be present in every valid report for the declared schema
  version, even when source data is partial or stale.
- Optional fields may be omitted only when the absence itself is expected and
  documented. If absence changes client behavior, prefer a required nullable
  field plus an explicit status or reason.
- Location, species, regulation, fish count, alert, warning, and source-health
  structures should keep stable identifiers so clients can compare reports across
  runs.
- Fields consumed by Kenai Pulse for legal status, score display, confidence,
  warnings, freshness, and source health must not change meaning without a major
  version bump.

## Timestamp Formatting

- Use ISO 8601 timestamps with timezone offsets or `Z` for UTC.
- `generated_at`, `expires_at`, `fetched_at`, `last_success_at`, `observed_at`,
  `effective_date`, and `expires_date` must have documented semantics.
- Report-level generated timestamps describe the report build. Source-level
  timestamps describe source observation, fetch, or last success time and must not
  be substituted for one another.
- Date-only fields such as regulation effective dates must remain date-only when
  time of day is not provided by the source.

## Null Handling

- Null means the engine does not have a validated value for the field.
- Null must not mean zero, normal, false, current, unrestricted, safe, or
  irrelevant.
- When a null value affects interpretation, pair it with a status, warning,
  confidence explanation, source-health item, or manual-review flag.
- Avoid replacing missing numeric data with defaults unless the default is a
  documented scoring prior and the report makes that prior visible.

## Enum Consistency

- Enum values are contract values. Keep spelling, casing, and meaning stable.
- Additive enum changes require client-tolerant handling and fixture coverage.
- Do not reuse an enum value for a narrower, broader, or different meaning.
- Preferred report enums should remain plain, predictable strings such as
  `excellent`, `good`, `fair`, `poor`, `restricted`, `closed`, `unknown`,
  `ok`, `degraded`, `failed`, `info`, `watch`, `warning`, and `critical`.

## Confidence Semantics

- Confidence must describe reliability of the generated environmental
  intelligence, not how optimistic the fishing prediction is.
- Confidence must decrease when required sources are stale, missing, failed,
  partially parsed, or manually reviewed.
- High score and high confidence are independent. Good fishing conditions with
  stale legal data must not appear as high-confidence guidance.
- Confidence explanations should identify the sources and failure modes that
  affected the value.

## Stale And Partial Data Semantics

- Stale data means a source was known previously but is older than its documented
  freshness threshold.
- Missing data means a required source or required field is not available for the
  current report.
- Partial data means some records were parsed or normalized while other expected
  records, fields, or classifications could not be validated.
- Stale, missing, and partial states must be machine-readable and app-facing when
  they affect legal status, safety, scoring, or confidence.

## Backward Compatibility

- Preserve existing field names, required fields, enum values, and null semantics
  within a schema version.
- New app-facing fields should be optional until client support is proven, unless
  the schema version is intentionally advanced.
- Maintain fixtures for the current production schema and representative degraded
  reports: stale legal source, stale water source, missing fish counts, PDF-only
  emergency order, and partial parser output.
- Fixture names should encode schema version and degradation state, such as
  `v1-normal.json`, `v1-stale-legal-source.json`,
  `v1-partial-adfg-parser.json`, and `v1-manual-review-eo.json`.
- Maintain a compatibility matrix for active and next schema versions that lists
  required fields, optional additions, deprecated fields, enum additions, and
  client action required.
- Do not force clients to infer a new meaning from old fields.

## Migration And Validation

- Every schema transition should include:
  - a short rationale;
  - before/after report examples;
  - validation model updates;
  - fixture updates;
  - app-consumption notes;
  - deprecation window and removal criteria when fields are being replaced;
  - compatibility matrix updates;
  - rollback expectations.
- Report validation must run as part of normal production generation and local
  quality checks.
- Validation should reject missing required fields, malformed timestamps,
  unknown enum values, invalid confidence ranges, invalid scores, and source
  health structures that cannot explain degraded report reliability.
