from __future__ import annotations

import sqlite3
from pathlib import Path

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
        connection.commit()
