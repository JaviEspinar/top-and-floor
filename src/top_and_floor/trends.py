"""Google Trends search interest, through the endpoints the Trends website uses.

There is no public API yet (Google's official one is an approval-only alpha),
so this can break or get rate limited without notice. Results are stored in
SQLite and reused for half a day to keep the number of requests low.
"""
import json
import logging
import time
from contextlib import closing

import httpx
import pandas as pd

from .db import connect

log = logging.getLogger(__name__)

BASE = "https://trends.google.com/trends"
TIMEFRAME = "today 5-y"  # weekly points, scaled so 100 is the 5 year peak
FRESH_SECONDS = 12 * 60 * 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS trends (
    keyword TEXT NOT NULL, timeframe TEXT NOT NULL,
    fetched_at REAL NOT NULL, points TEXT NOT NULL,
    PRIMARY KEY (keyword, timeframe)
) WITHOUT ROWID;
"""


def _unwrap(text: str) -> dict:
    # Responses start with an anti-JSON-hijacking prefix before the first brace.
    return json.loads(text[text.index("{"):])


def _fetch_remote(keyword: str) -> list[list]:
    """Finished weeks as [epoch seconds, interest 0 to 100]."""
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        # The explore endpoint only answers once the session has Google's cookie.
        client.get(f"{BASE}/?geo=US")
        request = {
            "comparisonItem": [{"keyword": keyword, "geo": "", "time": TIMEFRAME}],
            "category": 0,
            "property": "",
        }
        explore = client.get(f"{BASE}/api/explore", params={"hl": "en-US", "tz": 0, "req": json.dumps(request)})
        explore.raise_for_status()
        widget = next(w for w in _unwrap(explore.text)["widgets"] if w["id"] == "TIMESERIES")
        data = client.get(
            f"{BASE}/api/widgetdata/multiline",
            params={"hl": "en-US", "tz": 0, "req": json.dumps(widget["request"]), "token": widget["token"]},
        )
        data.raise_for_status()
    timeline = _unwrap(data.text)["default"]["timelineData"]
    # The current week is still filling up, so it would always look like a drop.
    return [[int(p["time"]), p["value"][0]] for p in timeline if not p.get("isPartial")]


def interest_over_time(keyword: str) -> pd.Series:
    """Weekly search interest for the keyword, empty when Google has no data."""
    key = (keyword.strip().lower(), TIMEFRAME)
    with closing(connect(SCHEMA)) as conn:
        row = conn.execute("SELECT fetched_at, points FROM trends WHERE keyword = ? AND timeframe = ?", key).fetchone()
        if row and time.time() - row[0] < FRESH_SECONDS:
            points = json.loads(row[1])
        else:
            try:
                points = _fetch_remote(key[0])
            except (httpx.HTTPError, KeyError, ValueError, StopIteration):
                if row is None:
                    raise
                log.warning("Google Trends unavailable, serving stored data for %r", keyword)
                points = json.loads(row[1])
            else:
                with conn:
                    conn.execute("INSERT OR REPLACE INTO trends VALUES (?, ?, ?, ?)", (*key, time.time(), json.dumps(points)))
    return pd.Series(
        [float(value) for _, value in points],
        index=pd.to_datetime([ts for ts, _ in points], unit="s"),
        dtype=float,
    )
