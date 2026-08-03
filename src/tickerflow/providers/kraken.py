"""Kraken OHLCV provider — crypto candlestick data from the public REST API.

Uses the ``/0/public/OHLC`` endpoint. No API key required.
Covers any crypto pair listed on Kraken (USDT, USD, EUR, BTC, ETH quotes).

Kraken uses ``XBT`` for Bitcoin internally, so ``BTCUSDT`` is normalised
to ``XBTUSDT`` before hitting the API.
"""

from __future__ import annotations

import logging
import re

import aiohttp

from tickerflow.models import Candle
from tickerflow.providers.base import OHLCVProvider

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.kraken.com/0/public/OHLC"

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

    No API key required. Covers crypto pairs quoted in USDT, USD, EUR,
    BTC, or ETH. Returns up to 720 bars per request.
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
            return None

        pair = _normalise(symbol)
        params = {"pair": pair, "interval": kraken_interval}

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(_BASE_URL, params=params) as resp,
            ):
                if resp.status != 200:
                    logger.warning("kraken HTTP %d for %s", resp.status, symbol)
                    return None
                data = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("kraken request failed for %s: %s", symbol, exc)
            return None

        if data.get("error"):
            logger.warning("kraken API error for %s: %s", symbol, data["error"])
            return None

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
