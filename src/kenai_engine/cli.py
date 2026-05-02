"""Command line interface for the Kenai condition engine."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterable
from datetime import date

from kenai_engine.config import Settings
from kenai_engine.db import connect, initialize_database
from kenai_engine.models import Alert, FishCount, Regulation, UsgsObservation
from kenai_engine.report_builder import build_placeholder_report, load_report, write_latest_report
from kenai_engine.sources.adfg_emergency_orders import (
    AdfgEmergencyOrdersAdapter,
    parse_emergency_orders,
)
from kenai_engine.sources.adfg_fish_counts import AdfgFishCountsAdapter, parse_fish_counts
from kenai_engine.sources.nws import NwsAdapter, parse_nws_alerts
from kenai_engine.sources.usgs import RawSnapshot, UsgsAdapter, parse_usgs_payload
from kenai_engine.storage.normalized_records import (
    list_normalized_records,
    save_normalized_record,
)
from kenai_engine.storage.raw_snapshots import get_latest_raw_snapshot, save_raw_snapshot
from kenai_engine.utils.logging import configure_logging
from kenai_engine.utils.time import utc_now

LOGGER = logging.getLogger(__name__)


def fetch(settings: Settings) -> None:
    """Run placeholder source fetches and store raw snapshots."""

    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    with connect(settings.db_path) as connection:
        initialize_database(connection)
        adapters = [
            UsgsAdapter(settings),
            AdfgEmergencyOrdersAdapter(settings),
            AdfgFishCountsAdapter(settings),
            NwsAdapter(settings),
        ]
        for adapter in adapters:
            try:
                snapshot = adapter.fetch()
            except Exception as exc:
                LOGGER.warning("fetch failed for %s: %s", adapter.source_name, exc)
                snapshot = RawSnapshot(
                    source=adapter.source_name,
                    fetched_at=utc_now().isoformat(),
                    payload=json.dumps({"error": str(exc), "placeholder": True}),
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


def build_report(settings: Settings) -> None:
    """Build and write the latest app-facing report."""

    with connect(settings.db_path) as connection:
        initialize_database(connection)
        observations = _latest_unique_usgs_observations(
            UsgsObservation.model_validate_json(row["payload"])
            for row in list_normalized_records(connection, "usgs_observation", limit=6)
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
    report = build_placeholder_report(
        usgs_observations=observations,
        regulations=regulations or None,
        fish_counts=fish_counts or None,
        alerts=alerts or None,
    )
    path = write_latest_report(settings.output_dir, report)
    LOGGER.info("wrote report to %s", path)


def validate(settings: Settings) -> None:
    """Validate that latest.json exists and matches the report schema."""

    path = settings.output_dir / "latest.json"
    if not path.exists():
        LOGGER.warning("%s does not exist; writing placeholder report first", path)
        write_latest_report(settings.output_dir)
    report = load_report(path)
    LOGGER.info("validated report for %s generated at %s", report.river, report.generated_at)


def run_daily(settings: Settings) -> None:
    """Run the current MVP daily pipeline."""

    fetch(settings)
    normalize(settings)
    build_report(settings)
    validate(settings)


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
        return

    for alert in alerts:
        save_normalized_record(connection, "alert", snapshot["fetched_at"], alert.model_dump_json())
    LOGGER.info("normalized %s NWS alerts", len(alerts))


def _regulation_from_order(order: dict[str, str]) -> Regulation:
    status = order.get("status")
    if status == "closure":
        regulation_status = "closed"
    elif status == "restriction":
        regulation_status = "restricted"
    else:
        regulation_status = "open"

    return Regulation(
        title=order["title"],
        status=regulation_status,
        source_url=order.get("url"),
        summary=order.get("summary") or order["title"],
    )


def _fish_count_from_record(record: dict[str, object]) -> FishCount | None:
    observation_date = _parse_date(str(record.get("observation_date", "")))
    if observation_date is None:
        return None

    return FishCount(
        species=str(record["species"]),
        location=str(record["location"]),
        count=int(record["count"]),
        observation_date=observation_date,
        source_url=str(record["source_url"]) if record.get("source_url") else None,
    )


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kenai-engine")
    parser.add_argument(
        "command",
        choices=["fetch", "normalize", "build-report", "run-daily", "validate"],
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
            case _:
                parser.error(f"unknown command: {args.command}")
    except Exception:
        LOGGER.exception("command failed: %s", args.command)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
