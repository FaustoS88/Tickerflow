"""In-memory TTL cache for OHLCV fetch results.

Caches provider responses keyed by (symbol, interval, limit) with
interval-aware expiry times — short intervals expire quickly, daily/weekly
bars are cached for hours.

The cache is module-level (process-scoped). Disable it entirely by setting
the environment variable ``OHLCV_CACHE_ENABLED=false``.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tickerflow.models import Candle

# TTL in seconds, keyed by interval string
_TTL: dict[str, int] = {
    "1m":  30,
    "5m":  120,
    "15m": 300,
    "30m": 600,
    "1h":  1_800,
    "4h":  7_200,
    "1d":  14_400,
    "1w":  86_400,
}

_DEFAULT_TTL = 60  # fallback for unmapped intervals

# Internal store: key → (expires_at, candles)
_store: dict[tuple[str, str, int], tuple[float, list[Candle]]] = {}


def is_enabled() -> bool:
    """Return True unless OHLCV_CACHE_ENABLED is explicitly set to 'false'."""
    return os.getenv("OHLCV_CACHE_ENABLED", "true").lower() != "false"


def ttl_for(interval: str) -> int:
    """Return the TTL in seconds for a given interval."""
    return _TTL.get(interval, _DEFAULT_TTL)


def get(symbol: str, interval: str, limit: int) -> list[Candle] | None:
    """Return cached candles if present and not expired, else None."""
    key = (symbol.upper(), interval, limit)
    entry = _store.get(key)
    if entry is None:
        return None
    expires_at, candles = entry
    if time.monotonic() > expires_at:
        del _store[key]
        return None
    return candles


def set(symbol: str, interval: str, limit: int, candles: list[Candle]) -> None:
    """Store candles in the cache with the appropriate TTL for the interval."""
    key = (symbol.upper(), interval, limit)
    _store[key] = (time.monotonic() + ttl_for(interval), candles)


def clear() -> None:
    """Evict all cached entries. Useful in tests and CLI resets."""
    _store.clear()


def size() -> int:
    """Return the number of entries currently in the cache."""
    return len(_store)
