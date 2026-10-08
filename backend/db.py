"""SQLite storage. Not implemented yet."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)
