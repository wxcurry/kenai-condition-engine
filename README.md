# Kenai Condition Engine

`kenai-condition-engine` is a standalone Python backend/data project for building app-facing Kenai River condition reports. The MVP skeleton prepares the shape of the system: source adapters, raw snapshot storage, normalized records, scoring, SQLite persistence, and JSON report output for an Android app.

## What It Does

- Runs local CLI commands for fetch, normalize, report generation, validation, and a daily pipeline.
- Produces `data/reports/latest.json` and `data/public/v1/latest.json` with stable
  fields the app can consume.
- Provides placeholder source adapters for USGS, Alaska Department of Fish and Game emergency orders, ADFG fish counts, and National Weather Service conditions.
- Applies deterministic MVP scoring, including regulation overrides for active closures and restrictions.

## What It Does Not Do

- It does not perform production scraping yet.
- It does not claim real-time regulatory accuracy.
- It does not require API keys.
- It does not replace official USGS, ADFG, NWS, or emergency-management sources.

## Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` if you want to override defaults. The skeleton also runs with built-in defaults.

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

In production, `data/public` can be uploaded to GitHub Pages, Cloudflare Pages,
S3, Firebase Hosting, or another static host. See
`docs/design/production_delivery.md`.

## Add A Source Adapter

1. Create a module under `src/kenai_engine/sources/`.
2. Add a small adapter class with `fetch()` and, when needed, parser helpers.
3. Return Pydantic models or plain dictionaries that can be validated by `models.py`.
4. Store raw responses through `storage/raw_snapshots.py`.
5. Add focused parser tests with small HTML or JSON fixtures.
6. Wire the adapter into `cli.py` after its behavior is tested.

## MVP Limitations

- Baseline regulations are MVP/manual-review context and are not legally complete.
- PDF-only ADF&G emergency orders are detected and marked for manual review, but
  PDF text extraction is not complete yet.
- SQLite tables are intentionally minimal.
- Scoring is deterministic but not biologically or hydrologically complete.
- Report summaries are simple strings, not generated analysis.
- No scheduler is included; use cron, launchd, or GitHub Actions later.

## Quality Checks

```bash
ruff check .
pytest
python -m kenai_engine.cli validate
python -m kenai_engine.cli run-daily
```
