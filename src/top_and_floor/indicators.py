"""Pure indicator maths on pandas series."""
import pandas as pd


def ema(series: pd.Series, span: int = 200) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI, the same smoothing TradingView uses."""
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss
    return (100 - 100 / (1 + rs)).where(loss != 0, 100.0)


def percentile_rank(series: pd.Series, window: int = 252) -> pd.Series:
    """Where today's value sits within the trailing window, from 0 to 100."""
    return series.rolling(window, min_periods=window // 2).rank(pct=True) * 100


def pct_change_over(series: pd.Series, periods: int) -> float | None:
    clean = series.dropna()
    if len(clean) <= periods:
        return None
    return float((clean.iloc[-1] / clean.iloc[-1 - periods] - 1) * 100)
