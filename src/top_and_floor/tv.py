"""TradingView access through the unofficial tvdatafeed library.

Everything that touches TradingView lives here, so a different price source
can replace it by providing the same functions: search(), daily_bars() and
daily_closes().

Every answer from TradingView is stored in a SQLite database. Bars are kept
forever and topped up with only the missing days, searches are kept for a day,
and stored data is served when TradingView is unreachable.
"""
import datetime as dt
import json
import logging
import sqlite3
import threading
import time
from contextlib import closing

import httpx
import pandas as pd
from tvDatafeed import Interval, TvDatafeed

from .db import connect

logging.getLogger("tvDatafeed.main").setLevel(logging.CRITICAL)
log = logging.getLogger(__name__)

SEARCH_URL = "https://symbol-search.tradingview.com/symbol_search/v3/"
BARS_FRESH_SECONDS = 30 * 60
SEARCH_FRESH_SECONDS = 24 * 60 * 60
SEARCH_STORED_RESULTS = 30
RETRIES = 4
# Bars re-downloaded on each top-up, to refresh the unfinished last bar and to
# detect history that TradingView rewrote (splits, dividends, data revisions).
OVERLAP_BARS = 5
BAR_COLUMNS = ["open", "high", "low", "close", "volume"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT NOT NULL, exchange TEXT NOT NULL, date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, exchange, date)
) WITHOUT ROWID;
-- One row per instrument: when it was last refreshed and how many bars the
-- deepest full download asked for.
CREATE TABLE IF NOT EXISTS bar_fetches (
    symbol TEXT NOT NULL, exchange TEXT NOT NULL,
    fetched_at REAL NOT NULL, depth INTEGER NOT NULL,
    PRIMARY KEY (symbol, exchange)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS searches (
    text TEXT NOT NULL, exchange TEXT NOT NULL,
    fetched_at REAL NOT NULL, results TEXT NOT NULL,
    PRIMARY KEY (text, exchange)
) WITHOUT ROWID;
"""

# TradingView drops connections when too many open at once.
_slots = threading.Semaphore(4)


class DataUnavailable(Exception):
    pass


def _fetch_remote(symbol: str, exchange: str, n_bars: int) -> pd.DataFrame:
    """Daily OHLCV indexed by date. Retries because the first attempt often drops."""
    df = None
    for attempt in range(RETRIES):
        with _slots:
            try:
                df = TvDatafeed().get_hist(symbol, exchange, interval=Interval.in_daily, n_bars=n_bars)
            except Exception:
                df = None
        if df is not None and not df.empty:
            break
        time.sleep(0.5 * (attempt + 1))
    if df is None or df.empty:
        raise DataUnavailable(f"TradingView returned no data for {exchange}:{symbol}")
    df = df[BAR_COLUMNS]
    df.index = pd.to_datetime(df.index).normalize()
    return df[~df.index.duplicated(keep="last")].sort_index()


def _store(conn: sqlite3.Connection, symbol: str, exchange: str, df: pd.DataFrame, depth: int, replace: bool) -> None:
    rows = [
        (symbol, exchange, ts.strftime("%Y-%m-%d"), *(None if pd.isna(v) else float(v) for v in values))
        for ts, values in zip(df.index, df[BAR_COLUMNS].itertuples(index=False))
    ]
    with conn:
        if replace:
            conn.execute("DELETE FROM bars WHERE symbol = ? AND exchange = ?", (symbol, exchange))
        conn.executemany("INSERT OR REPLACE INTO bars VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.execute(
            "INSERT OR REPLACE INTO bar_fetches VALUES (?, ?, ?, ?)", (symbol, exchange, time.time(), depth)
        )


def _read(conn: sqlite3.Connection, symbol: str, exchange: str, n_bars: int) -> pd.DataFrame:
    rows = conn.execute(
        "SELECT date, open, high, low, close, volume FROM bars "
        "WHERE symbol = ? AND exchange = ? ORDER BY date DESC LIMIT ?",
        (symbol, exchange, n_bars),
    ).fetchall()
    df = pd.DataFrame(rows[::-1], columns=["date", *BAR_COLUMNS])
    df.index = pd.to_datetime(df.pop("date"))
    df.index.name = "datetime"
    return df


def _history_rewritten(stored: pd.Series, fresh: pd.Series) -> bool:
    """True when finished bars we hold no longer match what TradingView serves."""
    common = stored.index.intersection(fresh.index)
    if common.empty:
        return True  # no overlap, so there may be a gap between old and new bars
    old, new = stored[common], fresh[common]
    return bool(((old - new).abs() > 1e-6 * new.abs().clip(lower=1)).any())


def _top_up(conn: sqlite3.Connection, symbol: str, exchange: str, depth: int) -> None:
    """Download only the days since the last stored bar."""
    stored = _read(conn, symbol, exchange, OVERLAP_BARS + 1)["close"]
    missing_days = (dt.date.today() - stored.index[-1].date()).days
    fresh = _fetch_remote(symbol, exchange, missing_days + OVERLAP_BARS)
    # The newest stored bar may have been saved before its session ended, so it
    # is allowed to differ. Older ones are final and must match.
    if _history_rewritten(stored.iloc[:-1], fresh["close"]):
        log.info("History changed for %s:%s, downloading it again", exchange, symbol)
        _store(conn, symbol, exchange, _fetch_remote(symbol, exchange, depth), depth, replace=True)
    else:
        _store(conn, symbol, exchange, fresh, depth, replace=False)


def daily_bars(symbol: str, exchange: str, n_bars: int = 1500) -> pd.DataFrame:
    """Daily OHLCV indexed by date, from the database when it is fresh enough."""
    with closing(connect(SCHEMA)) as conn:
        meta = conn.execute(
            "SELECT fetched_at, depth FROM bar_fetches WHERE symbol = ? AND exchange = ?", (symbol, exchange)
        ).fetchone()
        deep_enough = meta is not None and meta[1] >= n_bars
        if deep_enough and time.time() - meta[0] < BARS_FRESH_SECONDS:
            return _read(conn, symbol, exchange, n_bars)
        try:
            if deep_enough:
                _top_up(conn, symbol, exchange, meta[1])
            else:
                _store(conn, symbol, exchange, _fetch_remote(symbol, exchange, n_bars), n_bars, replace=True)
        except DataUnavailable:
            if meta is None:
                raise
            log.warning("TradingView unavailable for %s:%s, serving stored bars", exchange, symbol)
        return _read(conn, symbol, exchange, n_bars)


def daily_closes(symbol: str, exchange: str, n_bars: int = 1500) -> pd.Series:
    return daily_bars(symbol, exchange, n_bars)["close"]


def _search_remote(text: str, exchange: str) -> list[dict]:
    """tvdatafeed's own search uses a retired endpoint, so call the current one."""
    resp = httpx.get(
        SEARCH_URL,
        params={"text": text, "exchange": exchange, "hl": 0, "lang": "en", "domain": "production"},
        headers={"Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/"},
        timeout=15,
    )
    resp.raise_for_status()
    return [
        {
            "symbol": item["symbol"],
            "exchange": item.get("prefix") or item.get("exchange", ""),
            "type": item.get("type", ""),
            "description": item.get("description", ""),
        }
        for item in resp.json().get("symbols", [])[:SEARCH_STORED_RESULTS]
    ]


def search(text: str, limit: int = 8, exchange: str = "") -> list[dict]:
    key = (text.strip().lower(), exchange.strip().upper())
    with closing(connect(SCHEMA)) as conn:
        row = conn.execute("SELECT fetched_at, results FROM searches WHERE text = ? AND exchange = ?", key).fetchone()
        if row and time.time() - row[0] < SEARCH_FRESH_SECONDS:
            return json.loads(row[1])[:limit]
        try:
            results = _search_remote(*key)
        except httpx.HTTPError:
            if row is None:
                raise
            log.warning("TradingView search unavailable, serving stored results for %r", text)
            return json.loads(row[1])[:limit]
        with conn:
            conn.execute("INSERT OR REPLACE INTO searches VALUES (?, ?, ?, ?)", (*key, time.time(), json.dumps(results)))
        return results[:limit]
