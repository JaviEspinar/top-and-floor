# Top and Floor

A local dashboard that shows context indicators for any stock, ETF or crypto pair:

| Indicator | Source |
|---|---|
| Price vs EMA 200 | TradingView daily bars |
| Daily RSI (14) | TradingView daily bars |
| Dollar index (DXY) | TradingView `TVC:DXY` |
| US net liquidity | Fed balance sheet minus Treasury account minus reverse repo (TradingView FRED series) |
| Fear and greed, crypto | alternative.me |
| Sentiment, stocks and ETFs | Own 0 to 100 score from S&P 500 momentum, VIX, stocks vs treasuries and junk vs quality bonds |
| Public interest | Wikipedia pageviews, last 7 days against the 90 day average |

This is information, not financial advice.

## Run

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv run top-and-floor
```

Then open http://127.0.0.1:8000 and search for a symbol.

## Public interest card

Wikipedia rejects scripts that do not identify themselves. Set a contact (email or URL) before starting:

```sh
TOP_AND_FLOOR_CONTACT="you@example.com" uv run top-and-floor
```

## Notes

- Market data comes from TradingView through the unofficial [tvdatafeed](https://github.com/rongardF/tvdatafeed) library. It can break without notice and is meant for personal use only. All TradingView access lives in `src/top_and_floor/tv.py`, so another provider can replace it.
- `scripts/probe_tvdatafeed.py` checks which symbols the library can fetch today.
