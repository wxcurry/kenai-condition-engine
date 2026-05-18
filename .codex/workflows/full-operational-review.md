# Full Operational Review Workflow

## Purpose

Review operational reliability of ingestion, parser behavior, source-health
reporting, freshness handling, and failure transparency.

## Skills

- `.codex/skills/source-health-audit/SKILL.md`
- `.codex/skills/inspect-ingestion-pipeline/SKILL.md`

## Workflow

1. Inspect source health.
2. Inspect parser reliability only where source-health findings depend on parser
   diagnostics, parse coverage, or hidden parser failure modes.
3. Inspect observability.
4. Inspect stale-source handling.
5. Inspect failure transparency.
6. Inspect operational diagnostics.
7. Consolidate findings.
8. Prioritize reliability improvements.

## Consolidation Rules

- Rank official legal, safety, water, weather, fish count, and tide source risks
  above convenience or research sources.
- Prefer explicit degraded states over quiet fallbacks.
- Ensure source-health semantics remain compatible with the public report schema.
- Keep rendering and alert UI decisions in Kenai Pulse, not this workflow.
- Run `inspect-ingestion-pipeline` only when operational findings depend on
  parser correctness, source validation, normalization, or silent corruption
  risk.

## Expected Output

Produce a prioritized operational report with source-specific risks, missing
diagnostics, hidden failure modes, publish impact, escalation gaps, recommended
engine-side signals, and validation coverage.
