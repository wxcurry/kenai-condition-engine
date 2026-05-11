"""Seasonal source activation policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class FishCountRun:
    """Configured active window for an ADF&G fish-count run."""

    count_location_id: int
    species_id: int
    season_start: tuple[int, int]
    season_end: tuple[int, int]
    label: str

    def is_active_on(self, active_date: date) -> bool:
        start = date(active_date.year, *self.season_start)
        end = date(active_date.year, *self.season_end)
        return start <= active_date <= end


ADFG_FISH_COUNT_RUNS = (
    FishCountRun(72, 411, (5, 16), (6, 30), "Kenai River Chinook early run"),
    FishCountRun(72, 412, (7, 1), (8, 15), "Kenai River Chinook late run"),
    FishCountRun(40, 420, (7, 1), (8, 29), "Kenai River late-run sockeye"),
    FishCountRun(13, 421, (6, 4), (7, 14), "Russian River sockeye early run"),
    FishCountRun(13, 422, (7, 15), (9, 10), "Russian River sockeye late run"),
)


SEASONAL_SCORE_SOURCES = {"adfg_fish_counts"}


def active_fish_count_runs(active_date: date | None) -> tuple[FishCountRun, ...]:
    """Return ADF&G fish-count runs active on a date.

    Passing ``None`` keeps legacy behavior for callers that need the full configured
    source list instead of date-filtered active runs.
    """

    if active_date is None:
        return ADFG_FISH_COUNT_RUNS
    return tuple(run for run in ADFG_FISH_COUNT_RUNS if run.is_active_on(active_date))


def is_score_source_active(source: str, active_date: date) -> bool:
    """Return whether a score source should be required on a report date."""

    if source == "adfg_fish_counts":
        return bool(active_fish_count_runs(active_date))
    return True
