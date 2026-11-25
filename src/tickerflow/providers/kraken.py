"""Kraken OHLCV provider — crypto candlestick data from the public REST API.

Uses the ``/0/public/OHLC`` endpoint. No API key required.
Covers crypto pairs listed on Kraken and quoted in USDT, USDC, BTC, ETH or BNB.

Kraken uses ``XBT`` for Bitcoin internally, so ``BTCUSDT`` is normalised
to ``XBTUSDT`` before hitting the API.
"""

from __future__ import annotations

import re

import aiohttp

from tickerflow.errors import ProviderError
from tickerflow.models import Candle
from tickerflow.providers.base import HTTP_TIMEOUT, OHLCVProvider, utc

_BASE_URL = "https://api.kraken.com/0/public/OHLC"

#: Kraken serves only its most recent bars, whatever ``since`` says
_MAX_BARS = 720

_CRYPTO_RE = re.compile(r"^[A-Z]{2,}(USDT|USDC|BTC|ETH|BNB)$")

# tickerflow interval → Kraken interval (minutes)
_INTERVAL_MAP: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
}


def _normalise(symbol: str) -> str:
    """Map a generic crypto symbol to Kraken's pair format.

    Kraken uses ``XBT`` for Bitcoin, so ``BTCUSDT`` → ``XBTUSDT``.
    Everything else is uppercased and stripped of separators.
    """
    s = symbol.upper().replace("/", "").replace("-", "").strip()
    if s.startswith("BTC"):
        s = "XBT" + s[3:]
    return s


class KrakenProvider(OHLCVProvider):
    """Fetches OHLCV candles from the Kraken public REST API.

    No API key required. Covers crypto pairs quoted in USDT, USDC, BTC,
    ETH, or BNB. Serves its last 720 bars only, date ranges included.
    """

    name = "kraken"

    def supports(self, symbol: str) -> bool:
        return bool(_CRYPTO_RE.match(symbol.upper()))

    async def fetch(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> list[Candle] | None:
        kraken_interval = _INTERVAL_MAP.get(interval)
        if kraken_interval is None:
            raise ProviderError(f"no {interval} bars")

        pair = _normalise(symbol)
        params = {"pair": pair, "interval": kraken_interval}

        async with (
            aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session,
            session.get(_BASE_URL, params=params) as resp,
        ):
            if resp.status != 200:
                raise ProviderError(f"HTTP {resp.status}")
            data = await resp.json(content_type=None)

        if data.get("error"):
            raise ProviderError(f"API error: {', '.join(data['error'])}")

        result = data.get("result", {})
        # The result key is the Kraken pair name, which may differ from
        # the input (e.g. "XBTUSDT" → "XXBTUSDT" or similar). We pick
        # the first key that isn't "last".
        ohlc_key = next((k for k in result if k != "last"), None)
        if not ohlc_key:
            return None

        rows = result[ohlc_key]
        if not rows:
            return None

        # Kraken row layout:
        # [timestamp, open, high, low, close, vwap, volume, count]
        candles: list[Candle] = []
        for row in rows:
            try:
                candles.append(
                    Candle(
                        time=int(row[0]),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[6]),
                    )
                )
            except (IndexError, ValueError):
                continue

        return candles[-limit:] or None

    async def fetch_range(
        self,
        symbol: str,
        interval: str,
        start: int,
        end: int,
    ) -> list[Candle] | None:
        candles = await self.fetch(symbol, interval, _MAX_BARS)
        if not candles:
            return None
        # A full window may hide older bars that open at or after start
        full = len(candles) >= _MAX_BARS
        if full and start <= candles[0].time - _INTERVAL_MAP[interval] * 60:
            raise ProviderError(
                f"serves only its last {_MAX_BARS} {interval} bars, from {utc(candles[0].time)}"
            )
        return [c for c in candles if start <= c.time < end] or None
