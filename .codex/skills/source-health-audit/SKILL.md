---
name: source-health-audit
description: Use when reviewing Kenai Conditions Engine source-health output, stale-source visibility, parser diagnostics, or operational monitoring gaps.
---

# Source Health Audit

## Loads

- `.codex/agents/source-health-monitor.md`
- `.codex/agents/data-quality-auditor.md`
- `.codex/standards/source-ingestion-standards.md`
- `.codex/standards/schema-contract-standards.md`

## Routing

Use this skill when the primary concern is operational visibility, source-health
semantics, freshness policy, degradation severity, scheduled publishing,
last-known-good behavior, repeated source failures, or monitoring readiness. Use
`inspect-ingestion-pipeline` instead when the primary concern is parser
correctness, raw source validation, normalization, or silent data corruption.

## Workflow

1. Inspect source health reporting.
2. Inspect stale-source visibility.
3. Inspect parser diagnostics.
4. Inspect observability coverage.
5. Inspect publish-blocking criteria and repeated-failure escalation.
6. Identify weak operational visibility.
7. Identify hidden failure modes.
8. Improve diagnostics clarity.
9. Generate a prioritized operational report.

## Constraints

- Prioritize operational transparency.
- Surface uncertainty aggressively.
- Preserve report contract stability for source-health fields.
- Keep UI alert presentation and Android rendering behavior out of scope.

## Output

Return operational findings ordered by source criticality and user impact. Include
the source id, affected report surfaces, missing diagnostic, recommended
engine-side signal, validation strategy, and publish/monitoring implication.
