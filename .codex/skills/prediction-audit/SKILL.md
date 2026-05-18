---
name: prediction-audit
description: Use when reviewing Kenai Conditions Engine scoring, confidence, environmental modeling, weighting, overfitting, or predictive usefulness.
---

# Prediction Audit

## Loads

- `.codex/agents/prediction-engine-reviewer.md`
- `.codex/agents/fishing-condition-analyst.md`
- `.codex/standards/engine-architecture-standards.md`
- `.codex/standards/schema-contract-standards.md`

## Routing

Use this skill when the primary concern is score composition, weighting,
confidence semantics, legal gates, caps, deterministic explanations, or whether
current outputs could mislead users. Use `environmental-relationship-review`
instead when the primary concern is discovering, validating, or tiering new
environmental variables and correlations.

## Workflow

1. Inspect scoring systems.
2. Inspect weighting logic.
3. Inspect confidence calculations.
4. Inspect how already-accepted environmental relationships affect scores.
5. Identify weak weighting, hidden priors, duplicated modifiers, or unsupported
   confidence changes.
6. Identify overfitting risks in score mechanics.
7. Identify misleading outputs.
8. Identify angler usefulness gaps that require score or explanation changes.
9. Improve explainability.
10. Generate a prioritized improvement report.

## Constraints

- Avoid black-box scoring.
- Prioritize explainability and deterministic score reasons.
- Preserve user trust by surfacing uncertainty, stale data, and partial data.
- Prioritize fishing usefulness over novelty.
- Keep prediction logic inside the engine and out of Kenai Pulse.

## Output

Return prioritized recommendations grouped by scoring correctness, confidence
semantics, accepted relationship scoring impact, fishing usefulness, and schema
impact. Include any required tests or fixtures for each recommendation.
