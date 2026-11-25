"""Binance OHLCV provider — fetches klines from the Binance public REST API."""

from __future__ import annotations

import re

import aiohttp

from tickerflow.errors import ProviderError
from tickerflow.models import Candle
from tickerflow.providers.base import HTTP_TIMEOUT, OHLCVProvider, paginate

_KLINES_URL = "https://api.binance.com/api/v3/klines"

#: Most bars Binance returns per request
_PAGE = 1000

# Intervals accepted by Binance that tickerflow exposes
_VALID_INTERVALS = frozenset(
    {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}
)

# Crypto quote currencies handled by this provider
_CRYPTO_RE = re.compile(r"^[A-Z]{2,}(USDT|USDC|BTC|ETH|BNB|BUSD|FDUSD)$")

def _normalise(symbol: str) -> str:
    """Return a Binance-compatible symbol string.

    Strips slashes, hyphens, and whitespace then uppercases.
    Examples: ``BTC/USDT`` → ``BTCUSDT``, ``btc-usdt`` → ``BTCUSDT``.
    """
    return symbol.upper().replace("/", "").replace("-", "").strip()


class BinanceProvider(OHLCVProvider):
    """Fetches OHLCV klines from the Binance public REST API.

    No API key required. Covers any pair quoted in USDT, USDC, BTC, ETH,
    BNB, BUSD, or FDUSD. Requests past 1 000 bars (Binance's cap per call)
    and date ranges are paged back from the newest bar.
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
        candles = await self._walk(symbol, interval, limit=limit)
        return candles[-limit:] or None

    async def fetch_range(
        self,
        symbol: str,
        interval: str,
        start: int,
        end: int,
    ) -> list[Candle] | None:
        candles = await self._walk(symbol, interval, end=end - 1, start=start)
        return [c for c in candles if c.time >= start] or None

    async def _walk(
        self,
        symbol: str,
        interval: str,
        *,
        end: int | None = None,
        limit: int | None = None,
        start: int | None = None,
    ) -> list[Candle]:
        if interval not in _VALID_INTERVALS:
            raise ProviderError(f"no {interval} bars")
        ticker = _normalise(symbol)
        size = min(limit, _PAGE) if limit else _PAGE

        # One session per call, like the other providers: nothing stays bound to a closed event loop
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:

            async def page(before: int | None) -> list[Candle]:
                params: dict[str, str | int] = {"symbol": ticker, "interval": interval, "limit": size}
                if before is not None:
                    params["endTime"] = before * 1000 + 999
                async with session.get(_KLINES_URL, params=params) as resp:
                    if resp.status != 200:
                        raise ProviderError(f"HTTP {resp.status}")
                    data = await resp.json(content_type=None)
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
                    for row in data or []
                ]

            return await paginate(page, end=end, limit=limit, start=start)
