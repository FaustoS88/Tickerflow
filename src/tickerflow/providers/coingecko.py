"""CoinGecko OHLCV provider — crypto candlestick data, no API key required.

Uses the public ``/coins/{id}/ohlc`` endpoint, where CoinGecko picks the bar
size from the window: 1-2 days give 30-minute bars, 3-30 days 4-hour bars and
longer windows 4-day bars (daily bars need a paid plan). So only ``4h`` is
served, from a 30-day window. Prices are in the pair's quote currency, with
stablecoins priced in USD. CoinGecko stamps each bar at its close; candles here
carry the open time, like the exchanges.

Note: the OHLC endpoint does not include volume. All candles have ``volume=0``.
"""

from __future__ import annotations

import logging
import re

import aiohttp

from tickerflow.models import Candle
from tickerflow.providers.base import HTTP_TIMEOUT, OHLCVProvider

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

# Quote currency → CoinGecko vs_currency
_VS_CURRENCY: dict[str, str] = {
    "USDT": "usd",
    "USDC": "usd",
    "BUSD": "usd",
    "FDUSD": "usd",
    "BTC": "btc",
    "ETH": "eth",
    "BNB": "bnb",
}

_DAYS = 30  # a 3-30 day window gives 4-hour bars
_MAX_BARS = 180  # 30 days of 4h bars; longer requests go to the next provider
_BAR_SECONDS = 14_400


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

    Supported interval: ``4h``.

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
        if interval != "4h" or limit > _MAX_BARS:
            return None

        coin = _coin_id(symbol)
        if not coin:
            logger.debug("coingecko: no coin ID mapping for %s", symbol)
            return None

        url = f"{_BASE_URL}/coins/{coin}/ohlc"
        quote = _QUOTE_RE.search(symbol.upper())
        params = {"vs_currency": _VS_CURRENCY[quote.group()], "days": str(_DAYS)}

        try:
            async with (
                aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session,
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
                        time=int(row[0]) // 1000 - _BAR_SECONDS,  # close stamp → open time
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
