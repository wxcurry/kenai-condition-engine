# Kenai Condition Engine Initial Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a runnable Python backend/data skeleton for the Kenai River information engine.

**Architecture:** Use a simple `src/` package with Pydantic models at the boundary, stdlib argparse and sqlite3 for CLI/storage, placeholder source adapters, deterministic scoring, and report generation to `data/reports/latest.json`.

**Tech Stack:** Python 3.11+, Pydantic, httpx, BeautifulSoup/lxml, SQLite, pytest, ruff.

---

### Task 1: Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `README.md`
- Create: `data/raw/.gitkeep`
- Create: `data/reports/.gitkeep`

- [x] Add package metadata, dependencies, dev dependencies, ruff config, and pytest config.
- [x] Document MVP purpose, limitations, Android `latest.json` consumption, commands, and adapter extension workflow.

### Task 2: Models, Scoring, and Report Builder

**Files:**
- Create: `src/kenai_engine/models.py`
- Create: `src/kenai_engine/scoring.py`
- Create: `src/kenai_engine/report_builder.py`
- Test: `tests/test_scoring.py`
- Test: `tests/test_report_builder.py`

- [x] Write tests for closure/restriction overrides and report shape.
- [x] Implement deterministic score calculation and valid placeholder report output.

### Task 3: Config, Database, Storage, Sources, and CLI

**Files:**
- Create: `src/kenai_engine/config.py`
- Create: `src/kenai_engine/db.py`
- Create: `src/kenai_engine/cli.py`
- Create: source, storage, and utils modules.
- Test: adapter parser tests.

- [x] Add environment-backed settings.
- [x] Add SQLite initialization and storage helpers.
- [x] Add placeholder source adapters and CLI commands that run without source API keys.

### Task 4: Verification

- [x] Run `ruff check .`.
- [x] Run `pytest`.
- [x] Run `python -m kenai_engine.cli validate`.
- [x] Run `python -m kenai_engine.cli run-daily`.
- [x] Confirm `data/reports/latest.json` exists.
