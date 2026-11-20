"""Web app: a JSON API plus one static page."""
import asyncio
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import cards, favorites, trends, tv
from .indicators import ema, rsi

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Top and Floor")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/search")
def search(q: str) -> list[dict]:
    return tv.search(q)


class Favorite(BaseModel):
    symbol: str
    exchange: str
    type: str = ""
    description: str = ""


@app.get("/api/favorites")
def list_favorites() -> list[dict]:
    return favorites.all_favorites()


@app.put("/api/favorites")
def add_favorite(item: Favorite) -> list[dict]:
    favorites.add(item.symbol, item.exchange, item.type, item.description)
    return favorites.all_favorites()


@app.delete("/api/favorites")
def remove_favorite(symbol: str, exchange: str) -> list[dict]:
    favorites.remove(symbol, exchange)
    return favorites.all_favorites()


class TrendsTerm(BaseModel):
    symbol: str
    exchange: str
    term: str = ""


@app.put("/api/trends-term")
def set_trends_term(item: TrendsTerm) -> dict:
    """Choose the Google Trends search term for a symbol. Empty restores the automatic one."""
    trends.set_custom_term(item.symbol, item.exchange, item.term)
    return {"term": trends.custom_term(item.symbol, item.exchange)}


def _failed(key: str, title: str, exc: Exception) -> dict:
    return {
        "key": key,
        "title": title,
        "value": "n/a",
        "label": "Unavailable",
        "tone": "neutral",
        "detail": f"{type(exc).__name__}: {exc}",
        "series": [],
    }


async def _safe(key: str, title: str, fn, *args) -> dict:
    """One broken source must not take the whole dashboard down."""
    try:
        return await asyncio.to_thread(fn, *args)
    except Exception as exc:
        return _failed(key, title, exc)


@app.get("/api/dashboard")
async def dashboard(symbol: str, exchange: str = "", type: str = "", description: str = "") -> dict:
    if not exchange:
        if ":" in symbol:
            exchange, symbol = symbol.split(":", 1)
        matches = await asyncio.to_thread(tv.search, symbol, 8, exchange)
        if not matches:
            raise HTTPException(404, f"No TradingView symbol matches '{symbol}'")
        exact = [m for m in matches if m["symbol"].upper() == symbol.upper()]
        match = (exact or matches)[0]
        symbol, exchange = match["symbol"], match["exchange"]
        type, description = match["type"], match["description"]

    try:
        bars = await asyncio.to_thread(tv.daily_bars, symbol, exchange)
    except tv.DataUnavailable as exc:
        raise HTTPException(502, str(exc)) from exc

    close = bars["close"]
    crypto = cards.is_crypto(type)
    sentiment = cards.crypto_fear_greed_card if crypto else cards.stock_sentiment_card
    macro = await asyncio.gather(
        _safe("sentiment", "Fear and greed", sentiment),
        _safe("liquidity", "US net liquidity", cards.liquidity_card),
        _safe("dxy", "Dollar index (DXY)", cards.dxy_card),
        _safe("interest", "Public interest", cards.public_interest_card, symbol, exchange, type, description),
    )

    def line(series):
        return [
            {"time": ts.strftime("%Y-%m-%d"), "value": round(float(v), 6)}
            for ts, v in series.dropna().items()
        ]

    return {
        "symbol": f"{exchange}:{symbol}",
        "ticker": symbol,
        "exchange": exchange,
        "description": description,
        "type": type,
        "last": float(close.iloc[-1]),
        "last_date": close.index[-1].strftime("%Y-%m-%d"),
        "bars": [
            {"time": ts.strftime("%Y-%m-%d"), "open": r.open, "high": r.high, "low": r.low, "close": r.close}
            for ts, r in bars.iterrows()
        ],
        "ema200": line(ema(close, 200)),
        "rsi": line(rsi(close, 14)),
        "cards": [cards.ema200_card(close), cards.rsi_card(close), *macro],
    }


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000)
