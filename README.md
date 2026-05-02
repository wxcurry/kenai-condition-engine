# Kenai Condition Engine

`kenai-condition-engine` is a standalone Python backend/data project for building app-facing Kenai River condition reports. The MVP skeleton prepares the shape of the system: source adapters, raw snapshot storage, normalized records, scoring, SQLite persistence, and JSON report output for an Android app.

## What It Does

- Runs local CLI commands for fetch, normalize, report generation, validation, and a daily pipeline.
- Produces `data/reports/latest.json` with stable fields the app can consume.
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
```

An installed console entry point is also available:

```bash
kenai-engine run-daily
```

## Android App Consumption

The Android app should treat `data/reports/latest.json` as the current app-facing contract. It contains:

- `report_date`
- `generated_at`
- `river`
- `overall_score`
- `overall_status`
- `confidence`
- `summary`
- `locations`
- `regulations`
- `fish_counts`
- `alerts`
- `source_health`

In production, this file can be uploaded to static hosting or an API response. For now, it is generated locally by `build-report` and `run-daily`.

## Add A Source Adapter

1. Create a module under `src/kenai_engine/sources/`.
2. Add a small adapter class with `fetch()` and, when needed, parser helpers.
3. Return Pydantic models or plain dictionaries that can be validated by `models.py`.
4. Store raw responses through `storage/raw_snapshots.py`.
5. Add focused parser tests with small HTML or JSON fixtures.
6. Wire the adapter into `cli.py` after its behavior is tested.

## MVP Limitations

- Source adapters use placeholder data and parser stubs.
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
