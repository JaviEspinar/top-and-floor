"""TradingView access through the unofficial tvdatafeed library.

Everything that touches TradingView lives here, so a different price source
can replace it by providing the same two functions: search() and daily_closes()
/ daily_bars().
"""
import logging
import threading
import time

import httpx
import pandas as pd
from tvDatafeed import Interval, TvDatafeed

logging.getLogger("tvDatafeed.main").setLevel(logging.CRITICAL)

SEARCH_URL = "https://symbol-search.tradingview.com/symbol_search/v3/"
CACHE_SECONDS = 30 * 60
RETRIES = 4

_cache: dict[tuple[str, str, int], tuple[float, pd.DataFrame]] = {}
_cache_lock = threading.Lock()
# TradingView drops connections when too many open at once.
_slots = threading.Semaphore(4)


class DataUnavailable(Exception):
    pass


def daily_bars(symbol: str, exchange: str, n_bars: int = 1500) -> pd.DataFrame:
    """Daily OHLCV indexed by date. Retries because the first attempt often drops."""
    key = (symbol, exchange, n_bars)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]

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

    df = df.drop(columns=["symbol"])
    df.index = pd.to_datetime(df.index).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    with _cache_lock:
        _cache[key] = (time.time(), df)
    return df


def daily_closes(symbol: str, exchange: str, n_bars: int = 1500) -> pd.Series:
    return daily_bars(symbol, exchange, n_bars)["close"]


def search(text: str, limit: int = 8, exchange: str = "") -> list[dict]:
    """Symbol search. tvdatafeed's own search uses a retired endpoint."""
    resp = httpx.get(
        SEARCH_URL,
        params={"text": text, "exchange": exchange, "hl": 0, "lang": "en", "domain": "production"},
        headers={"Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/"},
        timeout=15,
    )
    resp.raise_for_status()
    results = []
    for item in resp.json().get("symbols", [])[:limit]:
        results.append(
            {
                "symbol": item["symbol"],
                "exchange": item.get("prefix") or item.get("exchange", ""),
                "type": item.get("type", ""),
                "description": item.get("description", ""),
            }
        )
    return results
