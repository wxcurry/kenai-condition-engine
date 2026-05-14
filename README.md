# Kenai Condition Engine

`kenai-condition-engine` is a standalone Python backend/data project for building production app-facing Kenai River condition reports. It fetches official source data, stores raw snapshots, normalizes records, scores conditions, persists data in SQLite, and writes versioned JSON reports for app consumption.

## What It Does

- Runs local CLI commands for fetch, normalize, report generation, validation, and a daily pipeline.
- Produces `data/reports/latest.json` and `data/public/v1/latest.json` with stable
  fields the app can consume.
- Fetches production source data from USGS, Alaska Department of Fish and Game emergency orders, ADF&G fish counts, National Weather Service, and NOAA tides.
- Applies deterministic production scoring, including regulation overrides for active closures and restrictions.

## Operational Boundaries

- It does not require API keys for the configured official/free sources.
- It keeps source-health, freshness, and manual-review warnings visible in the report contract.
- It is not a legal authority and should always point users back to official USGS, ADF&G, NWS, NOAA, and emergency-management sources for final decisions.

## Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` if you want to override defaults. The engine also runs with built-in production defaults.

## Run Commands

```bash
python -m kenai_engine.cli fetch
python -m kenai_engine.cli normalize
python -m kenai_engine.cli build-report
python -m kenai_engine.cli run-daily
python -m kenai_engine.cli validate
python -m kenai_engine.cli serve
```

An installed console entry point is also available:

```bash
kenai-engine run-daily
```

## Android App Consumption

The Android app should treat `data/public/v1/latest.json` as the static delivery
contract for app testing and hosting. `data/reports/latest.json` remains the
canonical local report artifact. The report contains:

- `schema_version` currently `1.0.0`
- `generated_by`
- `report_date`
- `generated_at`
- `river`
- `overall_score`
- `overall_status`
- `confidence`
- `summary`
- `locations`
- `baseline_regulations`
- `emergency_orders`
- `regulations` for backward compatibility with emergency orders
- `fish_counts`
- `alerts`
- `warnings`
- `source_health`

For local Android testing:

```bash
python -m kenai_engine.cli run-daily
python -m kenai_engine.cli serve
```

Then point the app at `http://127.0.0.1:8765/v1/latest.json` from the host
machine, or the Android emulator equivalent host address.

In production, Kenai Pulse should consume the GitHub Pages endpoint published by
this repository:

```text
https://wxcurry.github.io/kenai-condition-engine/v1/latest.json
```

The `Publish Live Report` GitHub Actions workflow refreshes that endpoint every
three hours by running `kenai-engine run-daily`, committing the generated
`data/public/v1/latest.json` back to `main`, and deploying `data/public`.
Treat `data/public/v1/latest.json` as a generated artifact: update it by running
the pipeline or letting the scheduled workflow commit it, not by hand-editing the
JSON.
GitHub Pages must be configured to use GitHub Actions as its deployment source.
See `docs/design/production_delivery.md`.

## Add A Source Adapter

1. Create a module under `src/kenai_engine/sources/`.
2. Add a small adapter class with `fetch()` and, when needed, parser helpers.
3. Return Pydantic models or plain dictionaries that can be validated by `models.py`.
4. Store raw responses through `storage/raw_snapshots.py`.
5. Add focused parser tests with small HTML or JSON fixtures.
6. Wire the adapter into `cli.py` after its behavior is tested.

## Production Notes

- Baseline regulation records are structured production context, but records marked `manual-review` must be reviewed against current ADF&G regulations before being presented as authoritative.
- PDF-only ADF&G emergency orders are detected and marked for manual review so the app can warn users when automated classification is incomplete.
- Scoring is deterministic and source-backed; source freshness and parser health directly affect confidence and warnings.
- GitHub Actions is the production scheduler for the Kenai Pulse live source.

## Quality Checks

```bash
ruff check .
pytest
python -m kenai_engine.cli validate
python -m kenai_engine.cli run-daily
```
