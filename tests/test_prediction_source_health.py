from datetime import UTC, datetime, timedelta

import pytest

from kenai_engine.models import SourceHealth
from kenai_engine.prediction import assess_prediction_source_state

GENERATED_AT = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("source_health", "expected_freshness", "expected_confidence", "expected_caution_fragment"),
    [
        (
            [
                SourceHealth(
                    source="adfg_emergency_orders",
                    status="ok",
                    last_checked_at=GENERATED_AT,
                    message="ok",
                )
            ],
            "fresh",
            "medium",
            "",
        ),
        (
            [
                SourceHealth(
                    source="adfg_emergency_orders",
                    status="ok",
                    last_checked_at=GENERATED_AT - timedelta(hours=30),
                    message="old",
                )
            ],
            "stale",
            "low",
            "stale",
        ),
        (
            [],
            "missing",
            "low",
            "missing",
        ),
        (
            [
                SourceHealth(
                    source="adfg_emergency_orders",
                    status="failed",
                    last_checked_at=GENERATED_AT,
                    message="timeout",
                )
            ],
            "missing",
            "low",
            "unavailable",
        ),
        (
            [
                SourceHealth(
                    source="adfg_emergency_orders",
                    status="degraded",
                    last_checked_at=GENERATED_AT,
                    message="Parser degraded.",
                )
            ],
            "stale",
            "low",
            "degraded",
        ),
        (
            [
                SourceHealth(
                    source="adfg_emergency_orders",
                    status="ok",
                    last_checked_at=GENERATED_AT,
                    message="ok",
                ),
                SourceHealth(
                    source="usgs",
                    status="ok",
                    last_checked_at=GENERATED_AT - timedelta(hours=12),
                    message="old water",
                ),
            ],
            "stale",
            "low",
            "stale",
        ),
    ],
)
def test_source_health_matrix_for_prediction_guardrails(
    source_health: list[SourceHealth],
    expected_freshness: str,
    expected_confidence: str,
    expected_caution_fragment: str,
) -> None:
    state = assess_prediction_source_state(GENERATED_AT, source_health)

    assert state.freshness == expected_freshness
    assert state.confidence == expected_confidence
    if expected_caution_fragment:
        assert any(expected_caution_fragment in caution.lower() for caution in state.cautions)
    else:
        assert state.cautions == []
