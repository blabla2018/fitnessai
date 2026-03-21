from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.db import connect_db, ensure_single_athlete, initialize_database
from app.intervals_client import IntervalsClient
from app.snapshot_builder import build_snapshot, export_snapshot_files
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
        "daily-sync",
        help="Run the recommended daily read-only Intervals sync for the last 3 days",
    )

    show_recent_parser = subparsers.add_parser(
        "show-recent-data", help="Show recently saved Intervals daily metrics"
    )
    show_recent_parser.add_argument("--days", type=int, default=7)

    export_parser = subparsers.add_parser(
        "export-snapshot",
        help="Export a compact JSON snapshot and a ready-to-paste prompt for manual AI use",
    )
    export_parser.add_argument(
        "--output-json",
        default="data/current_snapshot.json",
        help="Path to the JSON snapshot file",
    )
    export_parser.add_argument(
        "--output-prompt",
        default="data/current_prompt.txt",
        help="Path to the ready-to-paste prompt file",
    )

    return parser


def command_init_db() -> None:
    settings = get_settings()
    schema_path = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
    initialize_database(settings.database_path, schema_path)

    with connect_db(settings.database_path) as connection:
        athlete_id = ensure_single_athlete(
            connection=connection,
            display_name=settings.athlete_name,
            timezone=settings.athlete_timezone,
            external_id=settings.intervals_athlete_id,
        )

    print(f"Database initialized at: {settings.database_path}")
    print(f"Single athlete is ready with id={athlete_id}")


def command_show_config() -> None:
    settings = get_settings()
    print(f"app_name={settings.app_name}")
    print(f"athlete_name={settings.athlete_name}")
    print(f"athlete_timezone={settings.athlete_timezone}")
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
        request_pause_seconds=settings.intervals_request_pause_seconds,
    )

    with connect_db(settings.database_path) as connection:
        athlete_id = ensure_single_athlete(
            connection=connection,
            display_name=settings.athlete_name,
            timezone=settings.athlete_timezone,
            external_id=settings.intervals_athlete_id,
        )
        summary = sync_intervals_days(
            connection=connection,
            client=client,
            athlete_id=athlete_id,
            days=days,
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


def command_show_recent_data(days: int) -> None:
    settings = get_settings()
    with connect_db(settings.database_path) as connection:
        summary = summarize_recent_data(connection, days)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def command_export_snapshot(output_json: str, output_prompt: str) -> None:
    settings = get_settings()
    with connect_db(settings.database_path) as connection:
        snapshot = build_snapshot(connection)

    output_json_path = Path(output_json)
    output_prompt_path = Path(output_prompt)
    metric_date = snapshot["current_snapshot"]["metric_date"]
    dated_json_path = output_json_path.with_name(f"metrics_{metric_date}.json")
    prompt_template_path = (
        Path(__file__).resolve().parent.parent
        / "prompts"
        / "manual_analysis_prompt_template.txt"
    )
    export_snapshot_files(
        snapshot,
        output_json_path,
        output_prompt_path,
        prompt_template_path,
    )
    export_snapshot_files(
        snapshot,
        dated_json_path,
        output_prompt_path,
        prompt_template_path,
    )
    print(f"Snapshot JSON saved to: {output_json_path}")
    print(f"Dated snapshot JSON saved to: {dated_json_path}")
    print(f"Manual prompt saved to: {output_prompt_path}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        command_init_db()
    elif args.command == "show-config":
        command_show_config()
    elif args.command == "sync-intervals":
        command_sync_intervals(args.days)
    elif args.command == "daily-sync":
        command_sync_intervals(3)
    elif args.command == "show-recent-data":
        command_show_recent_data(args.days)
    elif args.command == "export-snapshot":
        command_export_snapshot(args.output_json, args.output_prompt)
    else:
        raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
