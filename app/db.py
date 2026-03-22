from __future__ import annotations

import sqlite3
from pathlib import Path


ATHLETE_METRICS_DAILY_ADDITIONAL_COLUMNS = {
    "sleep_quality_score": "REAL",
    "avg_sleeping_hr_bpm": "REAL",
    "hrv_sdnn_ms": "REAL",
    "vo2max": "REAL",
    "readiness_score": "REAL",
    "spo2_percent": "REAL",
    "respiration_rate": "REAL",
    "steps_count": "INTEGER",
    "ctl": "REAL",
    "atl": "REAL",
    "ramp_rate": "REAL",
    "ctl_load": "REAL",
    "atl_load": "REAL",
    "ride_eftp_watts": "REAL",
    "run_eftp": "REAL",
    "swim_eftp": "REAL",
}


def connect_db(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_path: Path, schema_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with connect_db(database_path) as connection:
        schema_sql = schema_path.read_text(encoding="utf-8")
        connection.executescript(schema_sql)
        _migrate_schema(connection)
        connection.commit()


def _migrate_schema(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(athlete_metrics_daily)")
    }
    for column_name, column_type in ATHLETE_METRICS_DAILY_ADDITIONAL_COLUMNS.items():
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE athlete_metrics_daily ADD COLUMN {column_name} {column_type}"
            )
