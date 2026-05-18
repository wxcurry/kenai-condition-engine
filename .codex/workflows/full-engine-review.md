# Full Engine Review Workflow

## Purpose

Run a complete engine-side review of ingestion, prediction, environmental
relationships, schema contracts, and source health without drifting into Kenai
Pulse frontend responsibilities.

## Skills

- `.codex/skills/inspect-ingestion-pipeline/SKILL.md`
- `.codex/skills/prediction-audit/SKILL.md`
- `.codex/skills/environmental-relationship-review/SKILL.md`
- `.codex/skills/schema-compatibility-review/SKILL.md`
- `.codex/skills/source-health-audit/SKILL.md`

## Workflow

1. Inspect ingestion pipeline.
2. Inspect prediction systems.
3. Inspect environmental relationships only when prediction or fishing findings
   depend on missing variables, weak correlations, historical assumptions, or
   relationship evidence tiers.
4. Inspect schema contracts.
5. Inspect source health.
6. Consolidate findings.
7. Rank improvements by impact.
8. Prioritize low-risk high-value improvements.

## Consolidation Rules

- Rank legal-status, safety, silent-corruption, and schema-breaking risks first.
- Separate engine responsibilities from Kenai Pulse rendering responsibilities.
- Prefer improvements that make reports more deterministic, explainable,
  observable, and contract-stable.
- Flag any recommendation that requires schema migration, new source authority,
  historical validation, or client coordination.
- Do not repeat the same review surface through multiple skills. If a narrow
  skill already produced sufficient findings, summarize and move on.
- Treat deep environmental relationship review as conditional research, not a
  mandatory second pass for every prediction audit.

## Expected Output

Produce a single prioritized report with sections for critical risks, high-value
improvements, schema impacts, validation gaps, and deferred research ideas.
