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
| Public interest | Google Trends searches, last finished week against the 12 month average |

This is information, not financial advice.

## Run

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv run top-and-floor
```

Then open http://127.0.0.1:8000 and search for a symbol.

## Public interest card

Search interest comes from the endpoints the Google Trends website uses, because Google's official Trends API is still an approval-only alpha. The search term is the coin name for crypto ("Bitcoin"), the ticker plus "stock" for stocks ("AAPL stock") and the ticker plus "ETF" for funds ("SPY ETF"). Results are stored for 12 hours.

When the automatic term is a poor fit, open "Change search term" on the card and save your own. It is remembered per symbol; "Use automatic" goes back to the default.

## Cache

Everything requested from TradingView and Google Trends is stored in a SQLite database at `data/cache.sqlite` (change it with `TOP_AND_FLOOR_DB`). Bars are kept and topped up with only the missing days once they are older than 30 minutes, symbol searches are kept for a day, and stored data is served when TradingView is unreachable. Delete the file to start clean.

## Favorites

Press the star next to a symbol's name to save it in the left column, and the cross next to a favorite to remove it. Favorites live in the same SQLite file as the cache, so deleting that file removes them too.

## Notes

- Market data comes from TradingView through the unofficial [tvdatafeed](https://github.com/rongardF/tvdatafeed) library. It can break without notice and is meant for personal use only. All TradingView access lives in `src/top_and_floor/tv.py`, so another provider can replace it.
- `scripts/probe_tvdatafeed.py` checks which symbols the library can fetch today, and `scripts/probe_google_trends.py` checks that Google Trends still answers.
