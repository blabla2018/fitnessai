from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.db import connect_db, initialize_database
from app.intervals_client import IntervalsClient
from app.snapshot_builder import build_snapshot, export_metrics_file
from app.sync_service import summarize_recent_data, sync_intervals_days


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fitness AI local app")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize the local SQLite database")
    subparsers.add_parser("show-config", help="Show resolved app configuration")
    sync_parser = subparsers.add_parser(
        "sync-intervals", help="Run a read-only Intervals sync"
    )
    sync_parser.add_argument("--days", type=int, default=7)
    subparsers.add_parser(
        "sync-last-week",
        help="Run the recommended read-only Intervals sync for the last 7 days",
    )

    show_recent_parser = subparsers.add_parser(
        "show-recent-data", help="Show recently saved Intervals daily metrics"
    )
    show_recent_parser.add_argument("--days", type=int, default=7)

    export_parser = subparsers.add_parser(
        "export-metrics",
        help="Export a dated metrics JSON file for AI analysis use",
    )
    export_parser.add_argument(
        "--output-dir",
        default="data",
        help="Directory where the dated metrics JSON file will be saved",
    )

    return parser


def command_init_db() -> None:
    settings = get_settings()
    schema_path = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
    initialize_database(settings.database_path, schema_path)

    print(f"Database initialized at: {settings.database_path}")
    print("Single-user database is ready")


def command_show_config() -> None:
    settings = get_settings()
    print(f"app_name={settings.app_name}")
    print(f"database_path={settings.database_path}")
    print(f"intervals_base_url={settings.intervals_base_url}")
    print(f"intervals_athlete_id={settings.intervals_athlete_id}")
    print(f"intervals_api_key_configured={bool(settings.intervals_api_key)}")


def command_sync_intervals(days: int) -> None:
    settings = get_settings()
    client = IntervalsClient(
        base_url=settings.intervals_base_url,
        athlete_id=settings.intervals_athlete_id,
        api_key=settings.intervals_api_key,
        request_pause_seconds=0.5,
    )

    with connect_db(settings.database_path) as connection:
        summary = sync_intervals_days(
            connection=connection,
            client=client,
            days=days,
            progress_callback=lambda message: print(message, flush=True),
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


def command_show_recent_data(days: int) -> None:
    settings = get_settings()
    with connect_db(settings.database_path) as connection:
        summary = summarize_recent_data(connection, days)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def command_export_metrics(output_dir: str) -> None:
    settings = get_settings()
    with connect_db(settings.database_path) as connection:
        snapshot = build_snapshot(connection)

    output_dir_path = Path(output_dir)
    metric_date = snapshot["current_week"]["days"][-1]["date"]
    output_json_path = output_dir_path / f"metrics_{metric_date}.json"
    export_metrics_file(snapshot, output_json_path)
    print(f"Metrics JSON saved to: {output_json_path}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        command_init_db()
    elif args.command == "show-config":
        command_show_config()
    elif args.command == "sync-intervals":
        command_sync_intervals(args.days)
    elif args.command == "sync-last-week":
        command_sync_intervals(7)
    elif args.command == "show-recent-data":
        command_show_recent_data(args.days)
    elif args.command == "export-metrics":
        command_export_metrics(args.output_dir)
    else:
        raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
