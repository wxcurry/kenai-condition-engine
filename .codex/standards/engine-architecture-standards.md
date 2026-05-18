# Engine Architecture Standards

These standards apply to the Kenai Conditions Engine and any Codex agent, skill,
workflow, or automation that changes engine behavior.

## Authority Boundary

- The Kenai Conditions Engine is the authoritative source of truth for fishing
  predictions, environmental scoring, confidence calculations, environmental
  relationship analysis, source ingestion, parser systems, report generation,
  data normalization, source health, and historical environmental interpretation.
- Prediction logic belongs only in this repository. Kenai Pulse consumes
  structured environmental intelligence reports; it must not duplicate or invent
  scoring rules, confidence logic, parser behavior, or environmental
  interpretations.
- Android UI, overlays, map presentation, user interaction design, mobile
  navigation UX, tourism presentation UI, and frontend rendering behavior belong
  exclusively to the Kenai Pulse app repository.
- Engine reports must be app-consumable without requiring the app to infer hidden
  rules. If the app needs a label, warning, confidence explanation, source status,
  or deterministic action cue, the engine should emit it explicitly.

## Prediction Principles

- Prioritize explainability over complexity. A less sophisticated model that can
  be audited and explained is preferred over a high-variance model that cannot.
- Avoid black-box environmental scoring. Every score change should trace back to
  source-backed inputs, documented thresholds, deterministic modifiers, legal
  overrides, or clearly labeled manual-review context.
- Preserve deterministic outputs for identical raw snapshots and configuration.
  Running the same report build against the same source snapshots should produce
  the same scores, classifications, warnings, confidence explanations, source
  health semantics, and schema structures.
- Allow nondeterminism only where it is explicitly unavoidable and contract-safe:
  source fetch time, report generation timestamps, live source changes, retry
  timing, and deployment metadata. These values must not change derived scoring
  semantics for the same raw inputs.
- Prioritize reliability over novelty. New data sources, formulas, or
  transformations must improve production usefulness without hiding fragile
  assumptions or increasing silent failure risk.
- Avoid misleading predictions. Never allow stale legal data, missing required
  environmental inputs, parser failures, or unsupported species assumptions to
  produce high-confidence fishing guidance.
- Avoid overfitting to isolated events. Single flood events, anecdotal guide
  reports, unusual run timing, or one-off source behavior must not become broad
  scoring rules without evidence across comparable conditions.

## Data Integrity

- Never fabricate missing environmental data. Missing values must remain missing,
  null, unknown, stale, degraded, or failed according to the report contract.
- Partial-data conditions must be surfaced clearly at the affected level: source,
  report, location, species, confidence explanation, warning, or alert.
- Stale-source conditions must be exposed explicitly. Staleness should lower
  confidence and, when relevant, add app-facing warnings that explain which
  source is stale and which decision surface it affects.
- Prefer explicit failures over silent degradation. A parser that cannot safely
  classify a regulation, count, alert, tide, or water record should emit a failure
  state or manual-review warning rather than guessing.
- All environmental relationships should be evidence-driven. If a relationship is
  inferred rather than directly measured, the report should label it as an
  inference and keep its scoring influence conservative.

## Environmental Evidence Tiers

- `validated`: Supported by repeated historical analysis, official source data,
  and tests or fixtures that demonstrate stable behavior across comparable
  conditions. Eligible for production scoring when explainable.
- `source-backed`: Supported by current official data or well-defined official
  records, but not yet historically calibrated. Eligible for conservative
  deterministic scoring or warnings.
- `inferred`: Derived from proxy signals such as rain as a clarity proxy or tide
  stage as a lower-river timing proxy. Eligible only for low-weight scoring,
  explicit explanations, or warnings.
- `hypothesis`: Plausible but not production-ready. Keep in research notes or
  improvement reports, not score drivers.
- `insufficient evidence`: Anecdotal, contradictory, too sparse, or not sourced
  well enough. Do not use for production scoring.

## Report Behavior

- Preserve schema compatibility. App-facing reports are production contracts, not
  internal implementation details.
- Maintain report contract stability. Field names, enum values, null semantics,
  confidence meanings, warning semantics, and source-health meanings must remain
  stable within a schema version.
- Preserve actionable fishing usefulness. Reports should answer practical
  angler-facing questions: legal status, safety, timing, water behavior, likely
  fishability, uncertainty, and what changed since the last reliable signal.
- Keep noisy metrics out of production outputs unless they improve decisions.
  Weak signals such as barometric trend, inferred crowding, or anecdotal reports
  should remain low-weight, labeled, or excluded until validated.
- Preserve maintainability and observability. New scoring or ingestion behavior
  should include clear tests, source provenance, parser diagnostics, validation
  paths, and operational signals.

## Change Review Checklist

- Does the change keep all prediction and interpretation logic in the engine?
- Does it avoid requiring Kenai Pulse to infer scoring, confidence, or source
  health?
- Does it make uncertainty visible instead of smoothing it away?
- Does it preserve deterministic behavior for identical inputs?
- Does it protect the existing report contract or include a deliberate schema
  migration plan?
- Does each new relationship have an evidence tier and a validation path?
- Does it explain why each environmental relationship is trustworthy enough for
  its scoring weight?
