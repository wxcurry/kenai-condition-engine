# Kenai Conditions Engine Codex System

This directory defines a modular Codex workflow system for the Kenai Conditions
Engine. It exists to make AI-assisted work on ingestion, scoring, confidence,
schema stability, and source health repeatable without blurring repository
boundaries.

## Engine Authority

The Kenai Conditions Engine is the authoritative source of truth for fishing
predictions, environmental scoring, confidence calculations, environmental
relationship analysis, source ingestion, parser systems, report generation, data
normalization, source health, and historical environmental interpretation.

Kenai Pulse consumes structured environmental intelligence reports from this
repository. The app owns Android UI, overlays, map presentation, mobile
navigation UX, tourism presentation UI, user interaction design, and frontend
rendering behavior. It should not invent prediction logic, confidence semantics,
source-health rules, or environmental interpretations.

Prediction logic belongs only in the engine so reports remain deterministic,
explainable, testable, source-backed, and consistent across every client.

## Directory Roles

- `agents/` contains specialized reviewer personas with narrow responsibilities.
- `skills/` combines agents and standards into reusable review procedures.
- `workflows/` orchestrates multiple skills into larger engine review passes.
- `standards/` captures repository-level rules that should shape future agent
  work.

## Agents

Agents remain specialized so reviews stay sharp:

- `fishing-condition-analyst` reviews practical fishing usefulness.
- `prediction-engine-reviewer` reviews scoring, weighting, confidence, and
  predictive quality.
- `data-quality-auditor` reviews ingestion, parser resilience, normalization, and
  missing-data handling.
- `schema-contract-guardian` protects report compatibility for external clients.
- `source-health-monitor` reviews observability, source freshness, parser health,
  and diagnostics.
- `environmental-relationship-researcher` reviews environmental interactions,
  missing variables, historical assumptions, and evidence quality.

Specialization prevents one broad agent from mixing prediction modeling, parser
reliability, schema compatibility, operational monitoring, and frontend concerns
into a single unfocused review.

## Skills

Skills combine the minimum agents needed for a recurring review:

- `inspect-ingestion-pipeline` primarily uses data quality expertise, with
  source-health support only where parser results affect operational visibility.
- `prediction-audit` primarily uses prediction expertise, with fishing usefulness
  support for practical output quality.
- `schema-compatibility-review` loads schema contract expertise.
- `source-health-audit` primarily uses operational source-health expertise, with
  data-quality support only where diagnostics depend on parser behavior.
- `environmental-relationship-review` primarily uses relationship research
  expertise, with fishing and prediction support for usefulness and score impact.

Each skill should produce prioritized findings with evidence, production impact,
engine-side recommendations, and validation expectations.

Use the narrowest skill that answers the question. Load adjacent skills only
when the finding crosses a real ownership boundary.

## Workflows

Workflows orchestrate skills for broader review passes:

- `full-engine-review` covers ingestion, prediction, relationships, schema, and
  source health, but deep relationship and parser passes are conditional.
- `full-prediction-review` focuses on scoring, confidence, environmental
  relationships, and fishing usefulness. It runs relationship research only when
  evidence or missing-variable questions remain.
- `full-operational-review` focuses on source health, parser reliability,
  observability, stale-source handling, and diagnostics. It runs ingestion review
  only when parser correctness or normalization is part of the operational risk.

Use workflows when the requested review crosses multiple skill boundaries. Use a
single skill when the task is narrow.

## Contributor Guidance

- Keep prediction, confidence, environmental interpretation, source ingestion,
  normalization, parser behavior, report generation, and source-health semantics
  in this repository.
- Keep Android UI, overlays, map rendering, mobile navigation UX, tourism
  presentation UI, and frontend behavior in Kenai Pulse.
- Preserve deterministic, explainable reports.
- Treat identical raw snapshots and configuration as requiring identical derived
  scores, warnings, confidence explanations, source-health semantics, and schema
  structures.
- Never fabricate missing environmental data.
- Surface stale, missing, partial, failed, and manual-review states clearly.
- Prefer explicit failures over silent degradation.
- Preserve schema compatibility unless a deliberate migration is planned.
- Keep environmental relationships evidence-driven and tiered as validated,
  source-backed, inferred, hypothesis, or insufficient evidence.
- Add tests or fixtures for degraded source states, parser drift, schema changes,
  and confidence changes.

## Future Expansion

- Add a `historical-calibration-analyst` agent after historical source archives
  are ready for systematic validation.
- Add a `legal-regulation-auditor` agent if baseline regulation parsing and
  emergency-order classification become more complex.
- Add a `report-fixture-review` skill for validating normal, stale, missing,
  partial, and manual-review report fixtures.
- Add a `release-contract-check` workflow that runs before schema changes,
  public report publishing, or Kenai Pulse integration updates.
