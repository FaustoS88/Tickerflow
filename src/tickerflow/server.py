"""Self-hosted market data API — ``tickerflow serve`` starts this on :8000.

Endpoints:
    GET /ohlcv/{symbol}?interval=1d&limit=100  — fetch OHLCV candles
    GET /providers/{symbol}                     — show the provider chain
    GET /health                                 — liveness check
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from tickerflow.registry import fetch as _fetch, pick, teardown


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    yield
    await teardown()


app = FastAPI(
    title="tickerflow",
    description="Self-hosted market data API — crypto, stocks, forex via automatic provider routing.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/providers/{symbol}")
async def providers(symbol: str) -> Any:
    """Return the ordered provider chain for a given symbol."""
    chain = pick(symbol.upper())
    return {"symbol": symbol.upper(), "providers": [p.name for p in chain]}


@app.get("/ohlcv/{symbol}")
async def ohlcv(
    symbol: str,
    interval: str = Query("1d", pattern=r"^(1m|5m|15m|1h|4h|1d|1w)$"),
    limit: int = Query(100, ge=1, le=5000),
) -> Any:
    """Fetch OHLCV candles for a symbol.

    Returns a JSON object with symbol metadata and an array of candle objects.
    """
    candles = await _fetch(symbol.upper(), interval, limit)

    if candles is None:
        raise HTTPException(
            status_code=404,
            detail=f"No data available for {symbol.upper()} at interval {interval}. "
            f"All providers failed.",
        )

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "count": len(candles),
        "candles": [
            {
                "time": c.time,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ],
    }
