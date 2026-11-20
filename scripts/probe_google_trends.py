"""Check whether Google Trends' unofficial web endpoints answer from this machine.

Run: uv run scripts/probe_google_trends.py [keyword]
"""
import json
import sys

import httpx

BASE = "https://trends.google.com/trends"


def interest_over_time(keyword: str, timeframe: str = "today 12-m") -> list[tuple[str, int]]:
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        # The explore endpoint only answers once the session has Google's cookie.
        client.get(f"{BASE}/?geo=US")
        request = {
            "comparisonItem": [{"keyword": keyword, "geo": "", "time": timeframe}],
            "category": 0,
            "property": "",
        }
        explore = client.get(f"{BASE}/api/explore", params={"hl": "en-US", "tz": 0, "req": json.dumps(request)})
        print("explore:", explore.status_code)
        explore.raise_for_status()
        # Responses start with an anti-JSON-hijacking prefix before the first brace.
        widgets = json.loads(explore.text[explore.text.index("{"):])["widgets"]
        widget = next(w for w in widgets if w["id"] == "TIMESERIES")
        data = client.get(
            f"{BASE}/api/widgetdata/multiline",
            params={"hl": "en-US", "tz": 0, "req": json.dumps(widget["request"]), "token": widget["token"]},
        )
        print("timeseries:", data.status_code)
        data.raise_for_status()
        timeline = json.loads(data.text[data.text.index("{"):])["default"]["timelineData"]
        return [(point["formattedAxisTime"], point["value"][0]) for point in timeline]


if __name__ == "__main__":
    points = interest_over_time(sys.argv[1] if len(sys.argv) > 1 else "Bitcoin")
    print(len(points), "points; first", points[0], "last", points[-1])
