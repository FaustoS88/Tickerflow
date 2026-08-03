"""Binance OHLCV provider — fetches klines from the Binance public REST API."""

from __future__ import annotations

import re

import aiohttp

from tickerflow.models import Candle
from tickerflow.providers.base import OHLCVProvider

_KLINES_URL = "https://api.binance.com/api/v3/klines"

# Intervals accepted by Binance that tickerflow exposes
_VALID_INTERVALS = frozenset(
    {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}
)

# Crypto quote currencies handled by this provider
_CRYPTO_RE = re.compile(r"^[A-Z]{2,}(USDT|USDC|BTC|ETH|BNB|BUSD|FDUSD)$")

# Module-level session — created once, reused across all requests
_session: aiohttp.ClientSession | None = None


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


def _normalise(symbol: str) -> str:
    """Return a Binance-compatible symbol string.

    Strips slashes, hyphens, and whitespace then uppercases.
    Examples: ``BTC/USDT`` → ``BTCUSDT``, ``btc-usdt`` → ``BTCUSDT``.
    """
    return symbol.upper().replace("/", "").replace("-", "").strip()


class BinanceProvider(OHLCVProvider):
    """Fetches OHLCV klines from the Binance public REST API.

    No API key required. Covers any pair quoted in USDT, USDC, BTC, ETH,
    BNB, BUSD, or FDUSD. Returns up to 1 000 bars per request (Binance cap).
    """

    name = "binance"

    def supports(self, symbol: str) -> bool:
        return bool(_CRYPTO_RE.match(_normalise(symbol)))

    async def fetch(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> list[Candle] | None:
        ticker = _normalise(symbol)

        if interval not in _VALID_INTERVALS:
            return None

        params = {
            "symbol": ticker,
            "interval": interval,
            "limit": min(limit, 1000),
        }

        session = await _get_session()
        async with session.get(_KLINES_URL, params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)

        if not data:
            return None

        # Binance kline row layout (positions 0-5):
        # [open_time_ms, open, high, low, close, volume, close_time_ms, ...]
        return [
            Candle(
                time=int(row[0]) // 1000,  # milliseconds → seconds
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in data
        ]
