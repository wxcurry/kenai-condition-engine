# Advisory Alert Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add advisory explanation and fishing impact fields to every report alert without adding a new top-level report field.

**Architecture:** Extend the `Alert` Pydantic model with two defaulted string fields. Enrich alerts in `report_builder` immediately before they are attached to the report, using deterministic helper functions for known advisory types and a generic fallback for unknown alerts.

**Tech Stack:** Python 3.11, Pydantic v2, pytest, existing report-builder module.

---

### Task 1: Alert Contract And Report Enrichment

**Files:**
- Modify: `src/kenai_engine/models.py`
- Modify: `src/kenai_engine/report_builder.py`
- Test: `tests/test_report_builder.py`

- [ ] **Step 1: Write the failing test**

Add tests asserting that generated alert JSON includes `advisory_explanation` and `fishing_impact`, and that flood/manual-review alerts use specific fishing impact copy.

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/wxc/Documents/GitHub/kenai-condition-engine/.venv/bin/python -m pytest tests/test_report_builder.py -k "advisory or manual_review" -q`

Expected: fail because `Alert` does not expose the new fields yet.

- [ ] **Step 3: Implement the minimal model and report-builder changes**

Add defaulted fields to `Alert`, enrich `active_alerts` in `build_condition_report`, and add helpers for flood, ADF&G manual-review, ADF&G fishing-report, and generic advisories.

- [ ] **Step 4: Run focused tests**

Run: `/Users/wxc/Documents/GitHub/kenai-condition-engine/.venv/bin/python -m pytest tests/test_report_builder.py -k "advisory or manual_review" -q`

Expected: selected report-builder tests pass.

- [ ] **Step 5: Run full report-builder tests**

Run: `/Users/wxc/Documents/GitHub/kenai-condition-engine/.venv/bin/python -m pytest tests/test_report_builder.py -q`

Expected: all report-builder tests pass.
