---
name: schema-compatibility-review
description: Use when reviewing Kenai Conditions Engine report structures, schema versions, field semantics, enum changes, or client compatibility risk.
---

# Schema Compatibility Review

## Loads

- `.codex/agents/schema-contract-guardian.md`
- `.codex/standards/schema-contract-standards.md`
- `.codex/standards/engine-architecture-standards.md`

## Routing

Use this skill for report contracts, schema versions, requiredness, enum values,
timestamp/null semantics, confidence semantics, fixture compatibility, and
client migration risk. Use other skills first only when the schema issue depends
on unresolved ingestion, prediction, or source-health behavior.

## Workflow

1. Inspect report structures.
2. Inspect field consistency across normal and degraded reports.
3. Inspect versioning.
4. Inspect backward compatibility.
5. Inspect enum consistency.
6. Inspect required-field stability.
7. Inspect deprecation windows and compatibility fixture coverage.
8. Identify breaking changes.
9. Generate a compatibility report.

## Constraints

- Preserve stable contracts.
- Avoid unnecessary schema churn.
- Treat nulls, timestamps, enum values, confidence, stale data, and partial data as
  contract semantics.
- Do not move interpretation work to Android clients.

## Output

Return compatibility findings ordered by client risk. For each finding include
the affected field or structure, whether it is breaking, expected schema version
impact, fixture coverage needed, and recommended migration path.
