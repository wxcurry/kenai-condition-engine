# ADF&G Fish Count JSON Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use normalized ADF&G Fish Counts JSON records to influence every supported species and mapped location score.

**Architecture:** Keep ADF&G JSON fetching/parsing as-is. Add a derived fish-count signal layer in `report_builder`, pass species/location signal maps through `ScoreInput`, and update deterministic scoring to apply species-sensitive biological adjustments. Preserve existing source-health confidence behavior.

**Tech Stack:** Python 3.11, Pydantic v2 models, pytest, existing deterministic scoring/report-builder modules.

---

### Task 1: Add Fish Count Signal Derivation

**Files:**
- Modify: `src/kenai_engine/report_builder.py`
- Test: `tests/test_report_builder.py`

- [x] **Step 1: Write failing signal behavior tests**

Add tests that build a report with Kenai sockeye, Kenai Chinook, and Russian sockeye `FishCount` records. Assert that lower Kenai gets Kenai count provenance, Russian River gets Russian count provenance, and Chinook receives a non-unknown supported species score when Chinook records exist.

- [x] **Step 2: Run the targeted tests**

Run: `pytest tests/test_report_builder.py -k "fish_count or chinook or russian" -v`

Expected before implementation: at least one new assertion fails because fish counts are still reduced mostly to sockeye.

- [x] **Step 3: Add internal signal helpers**

In `report_builder.py`, add a small internal dataclass:

```python
@dataclass(frozen=True)
class FishCountSignal:
    species_key: str
    location_key: str
    recent_avg: int
    latest_count: int
    trend: FishCountTrend
    latest_observation_date: date
    count_location_id: str | None = None
    species_id: str | None = None
```

Add helpers:

```python
def _fish_count_signals(fish_counts: list[FishCount]) -> list[FishCountSignal]:
    groups: dict[tuple[str, str], list[FishCount]] = {}
    for fish_count in fish_counts:
        species_key = _species_key(fish_count.species)
        location_key = _count_location_key(fish_count.location)
        if species_key is None or location_key is None:
            continue
        groups.setdefault((species_key, location_key), []).append(fish_count)
    return [_signal_from_group(species_key, location_key, group) for (species_key, location_key), group in groups.items()]

def _species_key(species: str) -> str | None:
    normalized = species.lower()
    if "sockeye" in normalized:
        return "sockeye"
    if "chinook" in normalized or "king" in normalized:
        return "chinook"
    if "coho" in normalized or "silver" in normalized:
        return "coho"
    return None

def _count_location_key(location: str) -> str | None:
    normalized = location.lower()
    if "russian" in normalized:
        return "russian"
    if "kenai" in normalized:
        return "kenai"
    if "kasilof" in normalized:
        return "kasilof"
    return None
```

Group by `(species_key, location_key)`, sort newest first, compute `recent_avg` from the newest three records, and reuse `_fish_count_trend`.

- [x] **Step 4: Run report-builder tests**

Run: `pytest tests/test_report_builder.py -v`

Expected after implementation: all report-builder tests pass.

### Task 2: Pass Signal Maps Into Scoring

**Files:**
- Modify: `src/kenai_engine/models.py`
- Modify: `src/kenai_engine/report_builder.py`
- Modify: `src/kenai_engine/scoring.py`
- Test: `tests/test_scoring.py`

- [x] **Step 1: Write failing scoring tests**

Add tests for:

```python
def test_chinook_count_signal_uses_lower_volume_thresholds():
    result = score_conditions(
        ScoreInput(
            species="chinook",
            fish_count_3day_avg_by_species={"chinook": 125},
            fish_count_trend_by_species={"chinook": "rising"},
        )
    )
    assert result.species_scores["chinook"] > result.species_scores["sockeye"]


def test_location_fish_count_adjustment_nudges_selected_location():
    result = score_conditions(
        ScoreInput(
            location="lower_kenai",
            fish_count_location_adjustments={"lower_kenai": 6},
        )
    )
    assert result.location_scores["lower_kenai"] > result.location_scores["upper_kenai"]
```

- [x] **Step 2: Run scoring tests**

Run: `pytest tests/test_scoring.py -k "fish_count or species_and_location" -v`

Expected before implementation: fields are missing on `ScoreInput`.

- [x] **Step 3: Extend `ScoreInput`**

Add fields:

```python
fish_count_3day_avg_by_species: dict[str, int] = Field(default_factory=dict)
fish_count_trend_by_species: dict[str, FishCountTrend] = Field(default_factory=dict)
fish_count_location_adjustments: dict[str, int] = Field(default_factory=dict)
```

- [x] **Step 4: Update scoring equations**

Update `_species_scores` to apply per-species averages/trends:

- sockeye: preserve existing high-volume thresholds.
- chinook/coho: use lower-volume thresholds and trend-sensitive adjustments.
- rainbow trout and Dolly Varden remain environmental-only unless future count records support them.

Update `_location_scores` to add bounded values from `fish_count_location_adjustments`.

- [x] **Step 5: Run scoring tests**

Run: `pytest tests/test_scoring.py -v`

Expected after implementation: all scoring tests pass.

### Task 3: Wire Report Construction To Signals

**Files:**
- Modify: `src/kenai_engine/report_builder.py`
- Test: `tests/test_report_builder.py`

- [x] **Step 1: Build signal maps in score input functions**

In `_score_input_from_records` and `_score_input_from_location_records`, derive signal maps from relevant fish counts:

```python
fish_count_3day_avg_by_species={signal.species_key: signal.recent_avg for signal in signals}
fish_count_trend_by_species={signal.species_key: signal.trend for signal in signals}
fish_count_location_adjustments={location_key: _fish_count_location_adjustment(signal)}
```

Keep the legacy `fish_count_3day_avg` and `fish_count_trend` fields populated for compatibility.

- [x] **Step 2: Update supported species reporting**

Use fish-count signals to decide which species have supported scores. Do not expose supported species scores for species without matching count records.

- [x] **Step 3: Improve provenance**

For matched location signals, continue exposing `source="adfg_fish_counts"`, `source_id=count_location_id`, `observed_at=latest_observation_date`, and `role="species_activity"`.

- [x] **Step 4: Run report tests**

Run: `pytest tests/test_report_builder.py -v`

Expected after implementation: all report-builder tests pass.

### Task 4: Full Verification And PR

**Files:**
- Modify as needed from test failures only.

- [x] **Step 1: Run full tests**

Run: `pytest -q`

Expected: all tests pass.

- [x] **Step 2: Run lint**

Run: `ruff check .`

Expected: no lint failures.

- [ ] **Step 3: Commit implementation**

Run:

```bash
git add src/kenai_engine/models.py src/kenai_engine/report_builder.py src/kenai_engine/scoring.py tests/test_report_builder.py tests/test_scoring.py docs/superpowers/plans/2026-05-13-adfg-fish-count-json-scoring.md
git commit -m "Use ADFG fish count signals across scores"
```

- [ ] **Step 4: Push branch and open PR**

Run:

```bash
git push -u origin codex/adfg-fish-count-json-scoring
gh pr create --title "Use ADFG fish count signals across scores" --body-file /tmp/adfg-fish-count-json-scoring-pr.md --base main --head codex/adfg-fish-count-json-scoring
```

- [ ] **Step 5: Review, repair, and merge**

Inspect PR diff and checks. Repair any actionable issues with focused commits, rerun affected tests, push fixes, then merge the PR after checks pass.
