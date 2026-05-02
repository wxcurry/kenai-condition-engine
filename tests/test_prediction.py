import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kenai_engine.models import Regulation, SourceHealth, SpotWindowPrediction
from kenai_engine.prediction import build_spot_window_predictions

GENERATED_AT = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


def test_prediction_matches_golden_spot_window_fixture() -> None:
    predictions = build_spot_window_predictions(
        generated_at=GENERATED_AT,
        spot_ids=["soldotna"],
        target_species="sockeye",
        source_health=[
            _health("adfg_emergency_orders", GENERATED_AT),
            _health("usgs", GENERATED_AT),
            _health("nws", GENERATED_AT),
        ],
        regulations=[],
    )

    payload = [prediction.model_dump(mode="json") for prediction in predictions]
    expected = json.loads(_fixture("golden_spot_window_predictions.json"))

    assert payload == expected
    SpotWindowPrediction.model_validate(payload[0])


def test_unknown_adfg_order_adds_conservative_legal_caution() -> None:
    prediction = build_spot_window_predictions(
        generated_at=GENERATED_AT,
        spot_ids=["soldotna"],
        target_species="sockeye",
        source_health=[_health("adfg_emergency_orders", GENERATED_AT)],
        regulations=[
            Regulation(
                title="Emergency Order 2-KS-UNKNOWN",
                status="unknown",
                effective_date=GENERATED_AT.date(),
                summary="Order could not be classified.",
                manual_review_required=False,
                content_type="html",
            )
        ],
    )[0]

    assert prediction.score_band == "unknown"
    assert prediction.confidence == "low"
    assert any("unknown" in caution.lower() for caution in prediction.legal_cautions)
    assert prediction.legal_status == "unknown"


def test_manual_review_adfg_order_adds_conservative_legal_caution() -> None:
    prediction = build_spot_window_predictions(
        generated_at=GENERATED_AT,
        spot_ids=["soldotna"],
        target_species="sockeye",
        source_health=[_health("adfg_emergency_orders", GENERATED_AT)],
        regulations=[
            Regulation(
                title="Emergency Order 2-KS-PDF",
                status="restricted",
                effective_date=GENERATED_AT.date(),
                source_url="https://www.adfg.alaska.gov/static/order.pdf",
                summary="PDF-only order.",
                manual_review_required=True,
                content_type="pdf",
            )
        ],
    )[0]

    assert prediction.score_band == "unknown"
    assert prediction.confidence == "low"
    assert prediction.legal_status == "restricted"
    assert any("manual review" in caution.lower() for caution in prediction.legal_cautions)


def test_stale_adfg_orders_reduce_confidence_and_add_caution() -> None:
    stale_checked_at = GENERATED_AT - timedelta(hours=30)

    prediction = build_spot_window_predictions(
        generated_at=GENERATED_AT,
        spot_ids=["soldotna"],
        target_species="sockeye",
        source_health=[_health("adfg_emergency_orders", stale_checked_at)],
        regulations=[],
    )[0]

    assert prediction.confidence == "low"
    assert prediction.freshness == "stale"
    assert any("stale" in caution.lower() for caution in prediction.legal_cautions)


def test_degraded_adfg_orders_reduce_confidence_and_add_caution() -> None:
    prediction = build_spot_window_predictions(
        generated_at=GENERATED_AT,
        spot_ids=["soldotna"],
        target_species="sockeye",
        source_health=[_health("adfg_emergency_orders", GENERATED_AT, status="degraded")],
        regulations=[],
    )[0]

    assert prediction.confidence == "low"
    assert prediction.freshness == "stale"
    assert any("degraded" in caution.lower() for caution in prediction.legal_cautions)


def test_closed_prediction_uses_closed_score_band() -> None:
    prediction = build_spot_window_predictions(
        generated_at=GENERATED_AT,
        spot_ids=["soldotna"],
        target_species="sockeye",
        source_health=[_health("adfg_emergency_orders", GENERATED_AT)],
        regulations=[
            Regulation(
                title="Emergency Order 2-KS-CLOSED",
                status="closed",
                effective_date=GENERATED_AT.date(),
                summary="Closed fishery.",
            )
        ],
    )[0]

    assert prediction.legal_status == "closed"
    assert prediction.score_band == "closed"
    assert prediction.condition_score == 0
    assert any("closure" in caution.lower() for caution in prediction.legal_cautions)


def _health(source: str, checked_at: datetime, status: str = "ok") -> SourceHealth:
    return SourceHealth(
        source=source,
        status=status,
        last_checked_at=checked_at,
        message=f"Fetched {source}.",
    )


def _fixture(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")
