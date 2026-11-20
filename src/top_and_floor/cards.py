"""One function per indicator. Each returns a card: a headline value, a label
that says how to read it, and a history series for the sparkline."""

import httpx
import pandas as pd

from . import trends, tv
from .indicators import ema, pct_change_over, percentile_rank, rsi, sma

CRYPTO_TYPES = {"spot", "crypto", "swap"}
HISTORY_POINTS = 365


def _points(series: pd.Series, last: int = HISTORY_POINTS) -> list[dict]:
    clean = series.dropna().tail(last)
    return [{"time": ts.strftime("%Y-%m-%d"), "value": round(float(v), 4)} for ts, v in clean.items()]


def _card(key: str, title: str, value: str, label: str, tone: str, detail: str, series: pd.Series | None) -> dict:
    """tone is 'bull', 'bear' or 'neutral' and only drives the label colour."""
    return {
        "key": key,
        "title": title,
        "value": value,
        "label": label,
        "tone": tone,
        "detail": detail,
        "series": _points(series) if series is not None else [],
    }


def is_crypto(asset_type: str) -> bool:
    return asset_type in CRYPTO_TYPES


def ema200_card(close: pd.Series) -> dict:
    line = ema(close, 200)
    if line.dropna().empty:
        return _card("ema200", "EMA 200", "n/a", "Not enough history", "neutral", "Needs 200 daily bars.", None)
    distance = (close / line - 1) * 100
    now = float(distance.iloc[-1])
    above = now >= 0
    return _card(
        "ema200",
        "Price vs EMA 200",
        f"{now:+.1f}%",
        "Above EMA 200" if above else "Below EMA 200",
        "bull" if above else "bear",
        f"EMA 200 at {line.iloc[-1]:,.2f}. Chart shows the distance in % over time.",
        distance,
    )


def rsi_card(close: pd.Series) -> dict:
    line = rsi(close, 14)
    now = float(line.iloc[-1])
    if now >= 70:
        label, tone = "Overbought", "bear"
    elif now <= 30:
        label, tone = "Oversold", "bull"
    else:
        label, tone = "Neutral", "neutral"
    return _card("rsi", "Daily RSI (14)", f"{now:.1f}", label, tone, "Above 70 is overbought, below 30 is oversold.", line)


def dxy_card() -> dict:
    close = tv.daily_closes("DXY", "TVC")
    line = ema(close, 200)
    above = close.iloc[-1] >= line.iloc[-1]
    month = pct_change_over(close, 21)
    return _card(
        "dxy",
        "Dollar index (DXY)",
        f"{close.iloc[-1]:.2f}",
        "Dollar strengthening" if above else "Dollar weakening",
        # A strong dollar is usually a headwind for risk assets.
        "bear" if above else "bull",
        f"{month:+.1f}% in a month, {'above' if above else 'below'} its EMA 200. A strong dollar tends to weigh on risk assets.",
        close,
    )


def liquidity_card() -> dict:
    """US net liquidity: Fed balance sheet minus Treasury account minus reverse repo."""
    fed = tv.daily_closes("WALCL", "FRED")
    tga = tv.daily_closes("WTREGEN", "FRED")
    rrp = tv.daily_closes("RRPONTSYD", "FRED")
    frame = pd.concat({"fed": fed, "tga": tga, "rrp": rrp}, axis=1).sort_index().ffill().dropna()
    net = (frame["fed"] - frame["tga"] - frame["rrp"]) / 1e12
    daily = net.resample("D").ffill()
    quarter = pct_change_over(daily, 91)
    rising = (quarter or 0) >= 0
    return _card(
        "liquidity",
        "US net liquidity",
        f"${net.iloc[-1]:.2f}tn",
        "Liquidity expanding" if rising else "Liquidity contracting",
        "bull" if rising else "bear",
        f"{quarter:+.1f}% in 3 months. Fed balance sheet minus Treasury account minus reverse repo.",
        daily,
    )


def crypto_fear_greed_card() -> dict:
    resp = httpx.get("https://api.alternative.me/fng/", params={"limit": HISTORY_POINTS}, timeout=15)
    resp.raise_for_status()
    rows = resp.json()["data"]
    series = pd.Series(
        {pd.Timestamp(int(r["timestamp"]), unit="s").normalize(): float(r["value"]) for r in rows}
    ).sort_index()
    return _sentiment_card("Crypto fear and greed", float(series.iloc[-1]), series, "Source: alternative.me.")


def stock_sentiment_card() -> dict:
    """Our own 0 to 100 score. CNN's index has no API and blocks automated clients,
    so this rebuilds four of its components from market data."""
    spx = tv.daily_closes("SPX", "SP")
    vix = tv.daily_closes("VIX", "TVC")
    tlt = tv.daily_closes("TLT", "NASDAQ")
    hyg = tv.daily_closes("HYG", "AMEX")
    lqd = tv.daily_closes("LQD", "AMEX")
    frame = pd.concat({"spx": spx, "vix": vix, "tlt": tlt, "hyg": hyg, "lqd": lqd}, axis=1).ffill().dropna()
    components = pd.DataFrame(
        {
            # S&P 500 against its 125 day average: higher means greed.
            "momentum": percentile_rank(frame["spx"] / sma(frame["spx"], 125)),
            # VIX against its 50 day average: higher means fear, so invert.
            "volatility": 100 - percentile_rank(frame["vix"] / sma(frame["vix"], 50)),
            # Stocks beating treasuries over 20 days means greed.
            "safe_haven": percentile_rank(frame["spx"].pct_change(20) - frame["tlt"].pct_change(20)),
            # Junk bonds beating investment grade over 20 days means greed.
            "junk_demand": percentile_rank(frame["hyg"].pct_change(20) - frame["lqd"].pct_change(20)),
        }
    )
    score = components.mean(axis=1, skipna=False)
    detail = "Own model, not CNN's index: S&P momentum, VIX, stocks vs treasuries, junk vs quality bonds."
    return _sentiment_card("Stock market sentiment", float(score.dropna().iloc[-1]), score, detail)


def _sentiment_card(title: str, now: float, series: pd.Series, detail: str) -> dict:
    if now < 25:
        label, tone = "Extreme fear", "bull"
    elif now < 45:
        label, tone = "Fear", "bull"
    elif now <= 55:
        label, tone = "Neutral", "neutral"
    elif now <= 75:
        label, tone = "Greed", "bear"
    else:
        label, tone = "Extreme greed", "bear"
    return _card("sentiment", title, f"{now:.0f}", label, tone, detail + " 0 is extreme fear, 100 is extreme greed.", series)


def trends_keyword(symbol: str, asset_type: str, description: str) -> str:
    """What people would type into Google when they get interested in the asset."""
    if is_crypto(asset_type):
        # "Bitcoin / TetherUS" should look up Bitcoin.
        return description.split(" / ")[0].strip() or symbol
    if asset_type == "fund":
        return f"{symbol} ETF"
    if asset_type == "stock":
        return f"{symbol} stock"
    return description or symbol


def public_interest_card(symbol: str, asset_type: str, description: str) -> dict:
    """Google searches: the last finished week against the 12 month average."""
    keyword = trends_keyword(symbol, asset_type, description)
    weekly = trends.interest_over_time(keyword)
    if weekly.empty or weekly.max() == 0:
        return _card(
            "interest", "Public interest", "n/a", "No search data", "neutral",
            f'Google Trends has too few searches for "{keyword}".', None,
        )
    now = float(weekly.iloc[-1])
    baseline = float(weekly.tail(52).mean())
    ratio = now / baseline if baseline else 1.0
    if ratio >= 1.5:
        label, tone = "Attention spike", "bear"
    elif ratio <= 0.7:
        label, tone = "Low attention", "bull"
    else:
        label, tone = "Normal attention", "neutral"
    return _card(
        "interest",
        "Public interest",
        f"{now:.0f}",
        label,
        tone,
        f'Google searches for "{keyword}", where 100 is the 5 year peak. '
        f"Last week is {ratio:.2f}x its 12 month average.",
        weekly,
    )
