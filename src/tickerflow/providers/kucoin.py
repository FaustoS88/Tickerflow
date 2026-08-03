"""KuCoin OHLCV provider — crypto candles via the public KuCoin REST API.

No API key required. Supports all standard intervals from 1m to 1w.
Endpoint: GET https://api.kucoin.com/api/v1/market/candles
"""

from __future__ import annotations

import logging
import re
import time

import aiohttp

from tickerflow.models import Candle
from tickerflow.providers.base import OHLCVProvider

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.kucoin.com/api/v1/market/candles"

_INTERVAL_MAP: dict[str, str] = {
    "1m":  "1min",
    "5m":  "5min",
    "15m": "15min",
    "30m": "30min",
    "1h":  "1hour",
    "4h":  "4hour",
    "1d":  "1day",
    "1w":  "1week",
}

# Approximate bar duration in seconds — used to compute startAt
_BAR_SECONDS: dict[str, int] = {
    "1m":  60,
    "5m":  300,
    "15m": 900,
    "30m": 1_800,
    "1h":  3_600,
    "4h":  14_400,
    "1d":  86_400,
    "1w":  604_800,
}

# KuCoin uses BASE-QUOTE format (e.g. BTC-USDT).
# Strip slashes and inject hyphen after the base currency.
_QUOTE_RE = re.compile(r"(USDT|USDC|BTC|ETH|BNB|BUSD|FDUSD)$", re.IGNORECASE)
# Broader pattern for normalisation — plain USD accepted in _normalise even if not in supports()
_NORMALISE_QUOTE_RE = re.compile(r"(USDT|USDC|BTC|ETH|BNB|BUSD|FDUSD|USD)$", re.IGNORECASE)


def _normalise(symbol: str) -> str:
    """Convert a symbol like ``BTCUSDT`` to KuCoin's ``BTC-USDT`` format."""
    s = symbol.upper().replace("/", "").replace("-", "")
    m = _NORMALISE_QUOTE_RE.search(s)
    if m:
        base = s[: m.start()]
        quote = m.group()
        return f"{base}-{quote}"
    return s


class KuCoinProvider(OHLCVProvider):
    """Fetches OHLCV candles from the KuCoin public REST API.

    Supports all crypto pairs listed on KuCoin. No API key required.
    Returns up to 1500 bars per request. All standard intervals supported.

    KuCoin candle row format (index order):
        [timestamp, open, close, high, low, volume, turnover]
    Note: close is index 2, high is index 3, low is index 4.
    """

    name = "kucoin"

    def supports(self, symbol: str) -> bool:
        up = symbol.upper()
        # Accept crypto pairs: ends in a known quote currency, no dot (intl stock)
        return bool(_QUOTE_RE.search(up) and "." not in up)

    async def fetch(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> list[Candle] | None:
        kucoin_interval = _INTERVAL_MAP.get(interval)
        if kucoin_interval is None:
            return None

        bar_sec = _BAR_SECONDS[interval]
        end_ts = int(time.time())
        start_ts = end_ts - bar_sec * int(limit * 1.3 + 5)

        kucoin_symbol = _normalise(symbol)
        params = {
            "symbol": kucoin_symbol,
            "type": kucoin_interval,
            "startAt": start_ts,
            "endAt": end_ts,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(_BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning("kucoin HTTP %d for %s", resp.status, kucoin_symbol)
                        return None
                    data = await resp.json()
        except Exception as exc:
            logger.warning("kucoin request failed for %s: %s", kucoin_symbol, exc)
            return None

        if data.get("code") != "200000":
            logger.warning("kucoin API error code=%s for %s", data.get("code"), kucoin_symbol)
            return None

        rows = data.get("data")
        if not rows:
            return None

        # KuCoin returns newest-first — reverse to get chronological order
        rows = list(reversed(rows))

        candles: list[Candle] = []
        for row in rows[-limit:]:
            try:
                candles.append(
                    Candle(
                        time=int(row[0]),
                        open=float(row[1]),
                        high=float(row[3]),
                        low=float(row[4]),
                        close=float(row[2]),
                        volume=float(row[5]),
                    )
                )
            except (IndexError, ValueError):
                continue

        return candles or None
