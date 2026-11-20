"""The one SQLite file that holds the caches and the favorites."""
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("TOP_AND_FLOOR_DB", "data/cache.sqlite"))


def connect(schema: str) -> sqlite3.Connection:
    """Open the database, creating the caller's tables when they are missing."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(schema)
    return conn
