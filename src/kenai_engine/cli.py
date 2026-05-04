"""Command line interface for the Kenai condition engine."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterable
from datetime import date
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from kenai_engine.baseline_regulations import load_baseline_regulations
from kenai_engine.config import Settings
from kenai_engine.db import connect, initialize_database
from kenai_engine.delivery import prepare_public_report
from kenai_engine.models import (
    Alert,
    FishCount,
    Regulation,
    SourceHealth,
    TidePrediction,
    UsgsFlowStatistic,
    UsgsObservation,
    WeatherObservation,
)
from kenai_engine.report_builder import build_placeholder_report, load_report, write_latest_report
from kenai_engine.sources.adfg_emergency_orders import (
    AdfgEmergencyOrdersAdapter,
    parse_emergency_orders,
)
from kenai_engine.sources.adfg_fish_counts import AdfgFishCountsAdapter, parse_fish_counts
from kenai_engine.sources.noaa_tides import NoaaTidesAdapter, parse_tide_predictions
from kenai_engine.sources.nws import NwsAdapter, parse_nws_alerts, parse_nws_weather
from kenai_engine.sources.usgs import (
    RawSnapshot,
    UsgsModernAdapter,
    UsgsStatisticsAdapter,
    parse_usgs_payload,
    parse_usgs_statistics_payload,
)
from kenai_engine.storage.normalized_records import (
    list_normalized_records,
    save_normalized_record,
)
from kenai_engine.storage.raw_snapshots import get_latest_raw_snapshot, save_raw_snapshot
from kenai_engine.storage.source_health import list_latest_source_health, save_source_health
from kenai_engine.utils.logging import configure_logging
from kenai_engine.utils.time import utc_now

LOGGER = logging.getLogger(__name__)


def fetch(settings: Settings) -> None:
    """Run placeholder source fetches and store raw snapshots."""

    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    with connect(settings.db_path) as connection:
        initialize_database(connection)
        adapters = [
            UsgsModernAdapter(settings),
            UsgsStatisticsAdapter(settings),
            AdfgEmergencyOrdersAdapter(settings),
            AdfgFishCountsAdapter(settings),
            NwsAdapter(settings),
            NoaaTidesAdapter(settings),
        ]
        for adapter in adapters:
            checked_at = utc_now().isoformat()
            try:
                snapshot = adapter.fetch()
            except Exception as exc:
                LOGGER.warning("fetch failed for %s: %s", adapter.source_name, exc)
                snapshot = RawSnapshot(
                    source=adapter.source_name,
                    fetched_at=checked_at,
                    payload=json.dumps({"error": str(exc), "placeholder": True}),
                )
                save_source_health(connection, adapter.source_name, checked_at, "error", str(exc))
            else:
                save_source_health(
                    connection,
                    adapter.source_name,
                    snapshot.fetched_at,
                    "ok",
                    "Fetched live source payload.",
                )
            save_raw_snapshot(connection, snapshot.source, snapshot.payload, snapshot.fetched_at)
            LOGGER.info("stored raw snapshot for %s", snapshot.source)


def normalize(settings: Settings) -> None:
    """Normalize available raw source snapshots."""

    with connect(settings.db_path) as connection:
        initialize_database(connection)
        snapshot = get_latest_raw_snapshot(connection, "usgs")
        if snapshot is not None:
            try:
                observations = parse_usgs_payload(snapshot["payload"])
            except Exception as exc:
                LOGGER.warning("could not normalize latest USGS snapshot: %s", exc)
                _save_normalize_failure(connection, "usgs", snapshot["fetched_at"], "USGS", exc)
            else:
                for observation in observations:
                    save_normalized_record(
                        connection,
                        "usgs_observation",
                        observation.observed_at.isoformat(),
                        observation.model_dump_json(),
                    )
                LOGGER.info("normalized %s USGS observations", len(observations))
        else:
            LOGGER.info("no USGS raw snapshot available to normalize")

        _normalize_adfg_emergency_orders(connection)
        _normalize_adfg_fish_counts(connection)
        _normalize_nws_alerts(connection)
        _normalize_nws_weather(connection)
        _normalize_usgs_statistics(connection)
        _normalize_noaa_tides(connection)


def build_report(settings: Settings) -> None:
    """Build and write the latest app-facing report."""

    with connect(settings.db_path) as connection:
        initialize_database(connection)
        observations = _latest_unique_usgs_observations(
            UsgsObservation.model_validate_json(row["payload"])
            for row in list_normalized_records(connection, "usgs_observation", limit=800)
            if json.loads(row["payload"]).get("site_id") in set(settings.usgs_site_ids)
        )
        regulations = [
            Regulation.model_validate_json(row["payload"])
            for row in list_normalized_records(connection, "regulation", limit=20)
        ]
        fish_counts = [
            FishCount.model_validate_json(row["payload"])
            for row in list_normalized_records(connection, "fish_count", limit=20)
        ]
        alerts = [
            Alert.model_validate_json(row["payload"])
            for row in list_normalized_records(connection, "alert", limit=20)
        ]
        weather = [
            WeatherObservation.model_validate_json(row["payload"])
            for row in list_normalized_records(connection, "weather_observation", limit=10)
        ]
        tides = [
            TidePrediction.model_validate_json(row["payload"])
            for row in list_normalized_records(connection, "tide_prediction", limit=20)
        ]
        flow_statistics = [
            UsgsFlowStatistic.model_validate_json(row["payload"])
            for row in list_normalized_records(connection, "usgs_flow_statistic", limit=400)
        ]
    source_health = _source_health_from_rows(list_latest_source_health(connection))
    baseline_regulations = load_baseline_regulations()
    report = build_placeholder_report(
        usgs_observations=observations,
        regulations=regulations,
        fish_counts=fish_counts,
        alerts=alerts,
        weather_observations=weather,
        tide_predictions=tides,
        usgs_flow_statistics=flow_statistics,
        source_health=source_health or None,
        baseline_regulations=baseline_regulations,
    )
    path = write_latest_report(settings.output_dir, report)
    public_path = prepare_public_report(report, settings.public_dir)
    LOGGER.info("wrote report to %s", path)
    LOGGER.info("wrote public report to %s", public_path)


def validate(settings: Settings) -> None:
    """Validate that latest.json exists and matches the report schema."""

    path = settings.output_dir / "latest.json"
    if not path.exists():
        LOGGER.warning("%s does not exist; writing placeholder report first", path)
        write_latest_report(settings.output_dir)
    try:
        report = load_report(path)
    except Exception as exc:
        LOGGER.warning("%s is invalid; regenerating latest report: %s", path, exc)
        write_latest_report(settings.output_dir)
        report = load_report(path)
    LOGGER.info("validated report for %s generated at %s", report.river, report.generated_at)


def run_daily(settings: Settings) -> None:
    """Run the current MVP daily pipeline."""

    fetch(settings)
    normalize(settings)
    build_report(settings)
    validate(settings)


def serve(settings: Settings) -> None:
    """Serve versioned public JSON for local Android/dev testing."""

    settings.public_dir.mkdir(parents=True, exist_ok=True)
    handler = partial(SimpleHTTPRequestHandler, directory=str(settings.public_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 8765), handler)
    LOGGER.info("serving %s at http://127.0.0.1:8765/", settings.public_dir)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("server stopped")


def _latest_unique_usgs_observations(
    observations: Iterable[UsgsObservation],
) -> list[UsgsObservation]:
    unique: dict[tuple[str, str], UsgsObservation] = {}
    for observation in observations:
        key = (observation.site_id, observation.parameter_code)
        unique.setdefault(key, observation)
    return list(unique.values())


def _normalize_adfg_emergency_orders(connection) -> None:
    snapshot = get_latest_raw_snapshot(connection, "adfg_emergency_orders")
    if snapshot is None:
        LOGGER.info("no ADFG emergency orders snapshot available to normalize")
        return

    try:
        orders = parse_emergency_orders(snapshot["payload"])
    except Exception as exc:
        LOGGER.warning("could not normalize latest ADFG emergency orders snapshot: %s", exc)
        _save_normalize_failure(
            connection,
            "adfg_emergency_orders",
            snapshot["fetched_at"],
            "ADF&G emergency orders",
            exc,
        )
        return

    normalized = [_regulation_from_order(order) for order in orders]
    for regulation in normalized:
        save_normalized_record(
            connection,
            "regulation",
            regulation.effective_date.isoformat()
            if regulation.effective_date is not None
            else snapshot["fetched_at"],
            regulation.model_dump_json(),
        )
    LOGGER.info("normalized %s ADFG emergency orders", len(normalized))


def _normalize_adfg_fish_counts(connection) -> None:
    snapshot = get_latest_raw_snapshot(connection, "adfg_fish_counts")
    if snapshot is None:
        LOGGER.info("no ADFG fish counts snapshot available to normalize")
        return

    try:
        parsed_counts = parse_fish_counts(snapshot["payload"])
    except Exception as exc:
        LOGGER.warning("could not normalize latest ADFG fish counts snapshot: %s", exc)
        _save_normalize_failure(
            connection,
            "adfg_fish_counts",
            snapshot["fetched_at"],
            "ADF&G fish counts",
            exc,
        )
        return

    normalized = [
        fish_count
        for record in parsed_counts
        if (fish_count := _fish_count_from_record(record)) is not None
    ]
    for fish_count in normalized:
        save_normalized_record(
            connection,
            "fish_count",
            fish_count.observation_date.isoformat(),
            fish_count.model_dump_json(),
        )
    LOGGER.info("normalized %s ADFG fish counts", len(normalized))


def _normalize_nws_alerts(connection) -> None:
    snapshot = get_latest_raw_snapshot(connection, "nws")
    if snapshot is None:
        LOGGER.info("no NWS snapshot available to normalize")
        return

    try:
        alerts = parse_nws_alerts(snapshot["payload"])
    except Exception as exc:
        LOGGER.warning("could not normalize latest NWS snapshot: %s", exc)
        _save_normalize_failure(connection, "nws", snapshot["fetched_at"], "NWS alerts", exc)
        return

    for alert in alerts:
        save_normalized_record(connection, "alert", snapshot["fetched_at"], alert.model_dump_json())
    LOGGER.info("normalized %s NWS alerts", len(alerts))


def _normalize_nws_weather(connection) -> None:
    snapshot = get_latest_raw_snapshot(connection, "nws")
    if snapshot is None:
        LOGGER.info("no NWS snapshot available to normalize weather")
        return

    try:
        weather_observations = parse_nws_weather(snapshot["payload"])
    except Exception as exc:
        LOGGER.warning("could not normalize latest NWS weather snapshot: %s", exc)
        _save_normalize_failure(connection, "nws", snapshot["fetched_at"], "NWS weather", exc)
        return

    for weather in weather_observations:
        save_normalized_record(
            connection,
            "weather_observation",
            weather.observed_at.isoformat(),
            weather.model_dump_json(),
        )
    LOGGER.info("normalized %s NWS weather observations", len(weather_observations))


def _normalize_usgs_statistics(connection) -> None:
    snapshot = get_latest_raw_snapshot(connection, "usgs_statistics")
    if snapshot is None:
        LOGGER.info("no USGS statistics snapshot available to normalize")
        return

    try:
        statistics = parse_usgs_statistics_payload(snapshot["payload"])
    except Exception as exc:
        LOGGER.warning("could not normalize latest USGS statistics snapshot: %s", exc)
        _save_normalize_failure(
            connection,
            "usgs_statistics",
            snapshot["fetched_at"],
            "USGS statistics",
            exc,
        )
        return

    for statistic in statistics:
        save_normalized_record(
            connection,
            "usgs_flow_statistic",
            f"{statistic.site_id}-{statistic.month:02d}-{statistic.day:02d}",
            statistic.model_dump_json(),
        )
    LOGGER.info("normalized %s USGS flow statistics", len(statistics))


def _normalize_noaa_tides(connection) -> None:
    snapshot = get_latest_raw_snapshot(connection, "noaa_tides")
    if snapshot is None:
        LOGGER.info("no NOAA tides snapshot available to normalize")
        return

    try:
        predictions = parse_tide_predictions(snapshot["payload"])
    except Exception as exc:
        LOGGER.warning("could not normalize latest NOAA tides snapshot: %s", exc)
        _save_normalize_failure(
            connection,
            "noaa_tides",
            snapshot["fetched_at"],
            "NOAA tides",
            exc,
        )
        return

    for prediction in predictions:
        save_normalized_record(
            connection,
            "tide_prediction",
            prediction.predicted_at.isoformat(),
            prediction.model_dump_json(),
        )
    LOGGER.info("normalized %s NOAA tide predictions", len(predictions))


def _regulation_from_order(order: dict[str, str]) -> Regulation:
    status = order.get("status")
    if status == "closure":
        regulation_status = "closed"
    elif status == "restriction":
        regulation_status = "restricted"
    elif status == "open":
        regulation_status = "open"
    else:
        regulation_status = "unknown"

    return Regulation(
        title=order["title"],
        status=regulation_status,
        effective_date=_parse_date(order.get("effective_date", "")),
        expires_date=_parse_date(order.get("expires_date", "")),
        source_url=order.get("url"),
        summary=order.get("summary") or order["title"],
        manual_review_required=order.get("manual_review_required") == "true"
        or regulation_status == "unknown",
        content_type=order.get("content_type", "html"),
    )


def _fish_count_from_record(record: dict[str, object]) -> FishCount | None:
    observation_date = _parse_date(str(record.get("observation_date", "")))
    if observation_date is None:
        return None

    return FishCount(
        species=str(record["species"]),
        location=str(record["location"]),
        count=int(record["count"]),
        daily_count=int(record["daily_count"]) if record.get("daily_count") is not None else None,
        cumulative_count=int(record["cumulative_count"])
        if record.get("cumulative_count") is not None
        else None,
        count_location_id=str(record["count_location_id"])
        if record.get("count_location_id") is not None
        else None,
        species_id=str(record["species_id"]) if record.get("species_id") is not None else None,
        method=str(record["method"]) if record.get("method") is not None else None,
        year=int(record["year"]) if record.get("year") is not None else None,
        observation_date=observation_date,
        source_url=str(record["source_url"]) if record.get("source_url") else None,
    )


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _source_health_from_rows(rows) -> list[SourceHealth]:
    return [
        SourceHealth(
            source=row["source"],
            status=_report_source_status(row["status"]),
            last_checked_at=row["checked_at"],
            message=row["message"],
            last_error=row["message"] if row["status"] == "error" else None,
        )
        for row in rows
    ]


def _report_source_status(stored_status: str) -> str:
    if stored_status == "error":
        return "failed"
    if stored_status == "placeholder":
        return "degraded"
    return "ok"


def _save_normalize_failure(
    connection,
    source: str,
    checked_at: str,
    label: str,
    exc: Exception,
) -> None:
    save_source_health(
        connection,
        source,
        checked_at,
        "error",
        f"Could not normalize latest {label} snapshot: {exc}",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kenai-engine")
    parser.add_argument(
        "command",
        choices=["fetch", "normalize", "build-report", "run-daily", "validate", "serve"],
        help="Command to run.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.from_env()

    try:
        match args.command:
            case "fetch":
                fetch(settings)
            case "normalize":
                normalize(settings)
            case "build-report":
                build_report(settings)
            case "run-daily":
                run_daily(settings)
            case "validate":
                validate(settings)
            case "serve":
                serve(settings)
            case _:
                parser.error(f"unknown command: {args.command}")
    except Exception:
        LOGGER.exception("command failed: %s", args.command)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
