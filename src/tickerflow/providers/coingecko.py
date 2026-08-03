"""CoinGecko OHLCV provider — crypto candlestick data, no API key required.

Uses the public ``/coins/{id}/ohlc`` endpoint. Granularity is determined
automatically by CoinGecko based on the requested time window:
  - 3-30 days  -> 4-hour bars
  - > 30 days  -> daily bars

Note: the OHLC endpoint does not include volume. All candles have ``volume=0``.
"""

from __future__ import annotations

import logging
import re

import aiohttp

from tickerflow.models import Candle
from tickerflow.providers.base import OHLCVProvider

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.coingecko.com/api/v3"

_CRYPTO_RE = re.compile(r"^[A-Z]{2,}(USDT|USDC|BTC|ETH|BNB|BUSD|FDUSD)$")
_QUOTE_RE = re.compile(r"(USDT|USDC|BUSD|FDUSD|BTC|ETH|BNB)$")

# Base currency → CoinGecko coin ID
_COIN_IDS: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "ADA": "cardano",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "AVAX": "avalanche-2",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "LTC": "litecoin",
    "ATOM": "cosmos",
    "XLM": "stellar",
    "NEAR": "near",
    "FIL": "filecoin",
    "APT": "aptos",
    "OP": "optimism",
    "ARB": "arbitrum",
}

# CoinGecko granularity is automatic based on `days`:
#   3-30  days -> 4-hour bars
#   > 30  days -> daily bars
_INTERVAL_DAYS: dict[str, int] = {
    "4h": 30,   # 30 days at 4h granularity → up to 180 bars
    "1d": 90,   # 90 days at daily granularity → up to 90 bars
}


def _base_currency(symbol: str) -> str | None:
    """Strip quote suffix and return the base currency.

    Examples: ``BTCUSDT`` → ``BTC``, ``ETHBTC`` → ``ETH``.
    """
    match = _QUOTE_RE.search(symbol.upper())
    return symbol[: match.start()].upper() if match else None


def _coin_id(symbol: str) -> str | None:
    base = _base_currency(symbol)
    return _COIN_IDS.get(base) if base else None


class CoinGeckoProvider(OHLCVProvider):
    """Fetches OHLCV candles from the CoinGecko public API.

    No API key required. Covers major crypto pairs quoted in USDT, USDC,
    BTC, ETH, BNB, BUSD, or FDUSD — provided the base currency is in the
    built-in coin ID map.

    Supported intervals: ``4h``, ``1d``.

    Volume is not available from the OHLC endpoint and is always ``0.0``.
    """

    name = "coingecko"

    def supports(self, symbol: str) -> bool:
        return bool(_CRYPTO_RE.match(symbol.upper())) and _coin_id(symbol) is not None

    async def fetch(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> list[Candle] | None:
        days = _INTERVAL_DAYS.get(interval)
        if days is None:
            return None

        coin = _coin_id(symbol)
        if not coin:
            logger.debug("coingecko: no coin ID mapping for %s", symbol)
            return None

        url = f"{_BASE_URL}/coins/{coin}/ohlc"
        params = {"vs_currency": "usd", "days": str(days)}

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(url, params=params) as resp,
            ):
                if resp.status != 200:
                    logger.warning(
                        "coingecko HTTP %d for %s (interval=%s)",
                        resp.status,
                        symbol,
                        interval,
                    )
                    return None
                data = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("coingecko request failed for %s: %s", symbol, exc)
            return None

        if not data:
            return None

        # Response rows: [timestamp_ms, open, high, low, close]
        candles: list[Candle] = []
        for row in data:
            try:
                candles.append(
                    Candle(
                        time=int(row[0]) // 1000,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=0.0,  # OHLC endpoint does not provide volume
                    )
                )
            except (IndexError, ValueError):
                continue

        return candles[-limit:] or None
