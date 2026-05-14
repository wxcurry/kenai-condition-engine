# Production Delivery

## Static JSON Delivery

The engine writes two report files:

- `data/reports/latest.json`: canonical local report artifact.
- `data/public/v1/latest.json`: app-consumable static JSON for Android and hosting.

`python -m kenai_engine.cli build-report` writes both files. `run-daily` fetches,
normalizes, builds, and validates the same contract. `serve` starts a local static
server rooted at `data/public` for development:

```bash
python -m kenai_engine.cli run-daily
python -m kenai_engine.cli serve
```

Local URL: `http://127.0.0.1:8765/v1/latest.json`.

The live Kenai Pulse source is published from this repository with GitHub Pages.
The scheduled workflow at `.github/workflows/publish-live-report.yml` runs the
full `run-daily` pipeline every three hours, uploads `data/public`, and deploys
that artifact with GitHub Pages. The same workflow commits the generated
`data/public/v1/latest.json` back to `main` so the tracked public report does
not drift from the deployed artifact.

Production URL:

```text
https://wxcurry.github.io/kenai-condition-engine/v1/latest.json
```

GitHub repository settings must use **Pages > Build and deployment > Source:
GitHub Actions**. The workflow can also be run manually from the Actions tab when
Kenai Pulse needs an immediate refresh.

## Schema Versioning

The current report schema is `1.0.0`. The top-level fields include:

- `schema_version`
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
- `regulations`
- `fish_counts`
- `alerts`
- `warnings`
- `source_health`

Validation requires `schema_version`; reports missing it fail Pydantic model
validation.

## Android Consumption Path

Android should consume `data/public/v1/latest.json` in development and
`https://wxcurry.github.io/kenai-condition-engine/v1/latest.json` in production.
Each location record is deterministic and remains present even when some source
data is missing. Location confidence and warning fields tell the UI when data is
incomplete.

The report includes `generated_at` and `expires_at`. Kenai Pulse should treat
responses past `expires_at` as stale and surface the report `warnings` or
`source_health` details instead of implying current conditions.

Location records include `id`, `name`, `segment`, `lat`, `lon`,
`fishing_context`, `condition_score`, `status`, `confidence`, `water`,
`weather`, `alerts`, and `notes`.

## Source-Health UI Mapping

Each `source_health` item includes app-facing fields:

- `status`: `ok`, `degraded`, or `failed`
- `severity`: `info`, `watch`, `warning`, or `critical`
- `user_title`
- `user_message`
- `last_success_at`
- `freshness_minutes`
- `last_error`
- `affects_score`
- `affects_legal_status`

The top-level `warnings` array is the Android-friendly list to show visibly.
Failed legal sources such as ADF&G emergency orders map to critical warnings.
Stale water, weather, fish count, tide, or historical flow data map to warning
or watch severity and reduce confidence through deterministic scoring.

## Baseline Regulation Limitations

Emergency orders are overrides, not the complete legal rule set. The production engine includes
`data/config/baseline_regulations.json` for structured baseline context, but the
included records are explicitly marked `manual-review` unless fully verified.
The app must not present baseline fields as complete legal advice.

Legal status order:

1. Baseline regulations provide default context.
2. Emergency orders override or modify the baseline.
3. Active closure forces `closed`.
4. Active restriction forces `restricted`.
5. Missing baseline records create a warning and reduce confidence.

## PDF And Manual-Review Limitations

ADF&G emergency orders may link only to PDFs. The production engine detects PDF URLs, stores
the URL/title/metadata, and marks the order with `manual_review_required`. The
report adds a visible warning and alert when this happens.

Future production options:

- Use `pdfplumber` for text extraction.
- Add OCR fallback for scanned PDFs.
- Add manual admin review and approval status.
- Store PDF checksums and alert when official documents change.

## Next Steps

1. Add Android model classes for schema `1.0.0`.
2. Add baseline regulation admin review workflow.
3. Add PDF extraction and checksum/change detection.
4. Split scoring into true per-location source matching when more gauges and
   location-specific signals are available.
