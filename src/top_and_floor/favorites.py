"""Symbols the user saved, kept in the same SQLite file as the TradingView cache."""
import time
from contextlib import closing

from .db import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS favorites (
    symbol TEXT NOT NULL, exchange TEXT NOT NULL,
    type TEXT NOT NULL, description TEXT NOT NULL, added_at REAL NOT NULL,
    PRIMARY KEY (symbol, exchange)
) WITHOUT ROWID;
"""


def all_favorites() -> list[dict]:
    with closing(connect(SCHEMA)) as conn:
        rows = conn.execute(
            "SELECT symbol, exchange, type, description FROM favorites ORDER BY added_at"
        ).fetchall()
    return [dict(zip(("symbol", "exchange", "type", "description"), row)) for row in rows]


def add(symbol: str, exchange: str, type: str, description: str) -> None:
    with closing(connect(SCHEMA)) as conn, conn:
        # Saving a favorite twice keeps its original position in the list.
        conn.execute(
            "INSERT OR IGNORE INTO favorites VALUES (?, ?, ?, ?, ?)",
            (symbol, exchange, type, description, time.time()),
        )


def remove(symbol: str, exchange: str) -> None:
    with closing(connect(SCHEMA)) as conn, conn:
        conn.execute("DELETE FROM favorites WHERE symbol = ? AND exchange = ?", (symbol, exchange))
