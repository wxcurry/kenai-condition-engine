---
name: environmental-relationship-review
description: Use when reviewing Kenai Conditions Engine environmental variables, fishing correlations, historical assumptions, or relationship weighting.
---

# Environmental Relationship Review

## Loads

- `.codex/agents/environmental-relationship-researcher.md`
- `.codex/agents/fishing-condition-analyst.md`
- `.codex/agents/prediction-engine-reviewer.md`
- `.codex/standards/engine-architecture-standards.md`

## Routing

Use this skill when the primary concern is discovering, validating, rejecting, or
tiering environmental variables, correlations, interactions, historical
assumptions, and proxy relationships. Use `prediction-audit` instead when the
relationship is already accepted and the question is how it affects score,
confidence, caps, or explanation mechanics.

## Workflow

1. Inspect current environmental variables.
2. Inspect relationship weighting.
3. Inspect historical assumptions.
4. Inspect overlooked interactions.
5. Identify weak assumptions.
6. Assign relationship evidence tiers.
7. Identify missing variables.
8. Identify potentially valuable correlations.
9. Generate a prioritized relationship report.

## Constraints

- Avoid pseudoscientific assumptions.
- Prioritize evidence-driven relationships.
- Avoid overfitting to isolated events.
- Keep hypothesis-level ideas out of production scoring until validated.
- Preserve explainable, deterministic report behavior.

## Output

Return relationship findings ordered by likely production value. Label each idea
as validated, source-backed, inferred, hypothesis, or insufficient evidence;
identify required validation data; and describe how uncertainty should appear in
the report contract.
