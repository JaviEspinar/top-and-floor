"""Check which symbols tvdatafeed can fetch today.

Run: uv run scripts/probe_tvdatafeed.py
"""
import logging

from tvDatafeed import Interval, TvDatafeed

logging.basicConfig(level=logging.ERROR)

SYMBOLS = [
    ("AAPL", "NASDAQ"),  # stock
    ("SPY", "AMEX"),  # ETF
    ("BTCUSDT", "BINANCE"),  # crypto
    ("DXY", "TVC"),  # dollar index
    ("VIX", "TVC"),  # volatility
    ("TOTAL", "CRYPTOCAP"),  # total crypto market cap
    ("WALCL", "FRED"),  # Fed balance sheet
    ("RRPONTSYD", "FRED"),  # reverse repo
    ("WTREGEN", "FRED"),  # Treasury general account
    ("M2SL", "FRED"),  # M2 money supply
]


def main() -> None:
    tv = TvDatafeed()
    for symbol, exchange in SYMBOLS:
        name = f"{exchange}:{symbol}"
        try:
            df = tv.get_hist(symbol, exchange, interval=Interval.in_daily, n_bars=5000)
        except Exception as exc:  # the probe reports every failure and keeps going
            print(f"{name}: ERROR {type(exc).__name__}: {exc}")
            continue
        if df is None or df.empty:
            print(f"{name}: EMPTY")
            continue
        print(
            f"{name}: {len(df)} bars, {df.index[0].date()} to {df.index[-1].date()}, "
            f"last close {df['close'].iloc[-1]}"
        )


if __name__ == "__main__":
    main()
