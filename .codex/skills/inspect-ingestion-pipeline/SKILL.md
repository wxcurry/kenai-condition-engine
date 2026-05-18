---
name: inspect-ingestion-pipeline
description: Use when reviewing Kenai Conditions Engine source ingestion, parser behavior, normalization, source freshness, or silent data corruption risk.
---

# Inspect Ingestion Pipeline

## Loads

- `.codex/agents/data-quality-auditor.md`
- `.codex/agents/source-health-monitor.md`
- `.codex/standards/source-ingestion-standards.md`
- `.codex/standards/engine-architecture-standards.md`

## Routing

Use this skill when the primary concern is parser correctness, source authority,
raw-to-normalized data integrity, parse coverage, retry behavior, or silent
corruption risk. Use `source-health-audit` instead when the primary concern is
operational visibility, scheduled publishing, degradation severity, alerting
readiness, or repeated source failures.

## Workflow

1. Inspect ingestion sources and source authority.
2. Inspect parser reliability, fixtures, and malformed-input behavior.
3. Inspect source freshness thresholds and freshness calculations.
4. Inspect parse coverage counts and skipped/failed record reasons.
5. Inspect stale-feed handling and confidence impact.
6. Inspect retry behavior and final failure reporting.
7. Inspect normalization logic for deterministic mappings and lossy transforms.
8. Identify silent corruption risks.
9. Identify missing observability that blocks parser maintenance.
10. Generate a prioritized findings report.

## Constraints

- Prioritize reliability over elegance.
- Avoid silent degradation and stale-but-plausible output.
- Preserve deterministic behavior for identical raw snapshots.
- Keep Android UI, map overlays, navigation, and presentation behavior out of
  scope.

## Output

Return findings ordered by production risk. For each finding include affected
source or parser, failure mode, user/report impact, evidence, and a concrete
engine-side recommendation.
