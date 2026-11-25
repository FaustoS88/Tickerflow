"""Self-hosted market data API — ``tickerflow serve`` starts this on :8000.

Endpoints:
    GET /ohlcv/{symbol}?interval=1d&limit=100  — fetch OHLCV candles
    GET /providers/{symbol}                     — show the provider chain
    GET /health                                 — liveness check
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import tickerflow
from tickerflow.errors import NoDataError
from tickerflow.registry import fetch as _fetch
from tickerflow.registry import pick

app = FastAPI(
    title="tickerflow",
    description="Self-hosted market data API — crypto, stocks, forex via automatic routing.",
    version=tickerflow.__version__,
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
    return {"symbol": symbol.upper(), "providers": chain}


@app.get("/ohlcv/{symbol}")
async def ohlcv(
    symbol: str,
    interval: str = Query("1d", pattern=r"^(1m|5m|15m|1h|4h|1d|1w)$"),
    limit: int = Query(100, ge=1, le=5000),
) -> Any:
    """Fetch OHLCV candles for a symbol.

    Returns a JSON object with symbol metadata, the provider that served the
    candles and an array of candle objects; 404 carries each provider's reason.
    """
    try:
        candles = await _fetch(symbol.upper(), interval, limit)
    except NoDataError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "provider": candles.provider,
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
