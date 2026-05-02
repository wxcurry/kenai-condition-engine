"""Command line interface for the Kenai condition engine."""

from __future__ import annotations

import argparse
import logging
import sys

from kenai_engine.config import Settings
from kenai_engine.db import connect, initialize_database
from kenai_engine.report_builder import load_report, write_latest_report
from kenai_engine.sources.adfg_emergency_orders import AdfgEmergencyOrdersAdapter
from kenai_engine.sources.adfg_fish_counts import AdfgFishCountsAdapter
from kenai_engine.sources.nws import NwsAdapter
from kenai_engine.sources.usgs import UsgsAdapter
from kenai_engine.storage.raw_snapshots import save_raw_snapshot
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
            snapshot = adapter.fetch()
            save_raw_snapshot(connection, snapshot.source, snapshot.payload, snapshot.fetched_at)
            LOGGER.info("stored placeholder snapshot for %s", snapshot.source)


def normalize(settings: Settings) -> None:
    """Placeholder normalization command."""

    with connect(settings.db_path) as connection:
        initialize_database(connection)
    LOGGER.info("normalization placeholder completed at %s", utc_now().isoformat())


def build_report(settings: Settings) -> None:
    """Build and write the latest app-facing report."""

    path = write_latest_report(settings.output_dir)
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
