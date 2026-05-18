# Full Prediction Review Workflow

## Purpose

Review predictive quality, scoring logic, environmental relationships,
confidence calculations, and fishing usefulness for engine-generated reports.

## Skills

- `.codex/skills/prediction-audit/SKILL.md`
- `.codex/skills/environmental-relationship-review/SKILL.md`

## Workflow

1. Inspect scoring systems.
2. Inspect accepted environmental relationships only as they affect scoring and
   confidence mechanics.
3. Inspect confidence calculations.
4. Inspect weighting assumptions.
5. Inspect predictive usefulness.
6. Identify weak correlations that require a separate relationship review.
7. Identify misleading outputs.
8. Consolidate findings.
9. Prioritize prediction improvements.

## Consolidation Rules

- Treat legal and safety overrides as hard gates.
- Keep weak or inferred relationships conservative and clearly labeled.
- Prefer explainable deterministic improvements over opaque model complexity.
- Separate validated scoring improvements from research opportunities.
- Run `environmental-relationship-review` only when the audit depends on
  relationship discovery, evidence tiering, historical validation, or missing
  variables.

## Expected Output

Produce a prioritized prediction report with findings for score correctness,
confidence reliability, environmental relationship quality, fishing usefulness,
validation needs, and any relationship questions that require a deep follow-up.
