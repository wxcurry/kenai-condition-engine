"""Command line interface for the Kenai condition engine."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterable

from kenai_engine.config import Settings
from kenai_engine.db import connect, initialize_database
from kenai_engine.models import UsgsObservation
from kenai_engine.report_builder import build_placeholder_report, load_report, write_latest_report
from kenai_engine.sources.adfg_emergency_orders import AdfgEmergencyOrdersAdapter
from kenai_engine.sources.adfg_fish_counts import AdfgFishCountsAdapter
from kenai_engine.sources.nws import NwsAdapter
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
        if snapshot is None:
            LOGGER.info("no USGS raw snapshot available to normalize")
            return

        try:
            observations = parse_usgs_payload(snapshot["payload"])
        except Exception as exc:
            LOGGER.warning("could not normalize latest USGS snapshot: %s", exc)
            return

        for observation in observations:
            save_normalized_record(
                connection,
                "usgs_observation",
                observation.observed_at.isoformat(),
                observation.model_dump_json(),
            )
        LOGGER.info("normalized %s USGS observations", len(observations))


def build_report(settings: Settings) -> None:
    """Build and write the latest app-facing report."""

    with connect(settings.db_path) as connection:
        initialize_database(connection)
        observations = _latest_unique_usgs_observations(
            UsgsObservation.model_validate_json(row["payload"])
            for row in list_normalized_records(connection, "usgs_observation", limit=6)
        )
    report = build_placeholder_report(usgs_observations=observations)
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
