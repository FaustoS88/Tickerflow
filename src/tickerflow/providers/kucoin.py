"""KuCoin OHLCV provider — crypto candles via the public KuCoin REST API.

No API key required. Supports all standard intervals from 1m to 1w.
Endpoint: GET https://api.kucoin.com/api/v1/market/candles
"""

from __future__ import annotations

import re
import time

import aiohttp

from tickerflow.errors import ProviderError
from tickerflow.models import Candle
from tickerflow.providers.base import HTTP_TIMEOUT, OHLCVProvider, paginate

#: Most bars KuCoin returns per request
_PAGE = 1500

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
    All standard intervals supported. Requests past 1 500 bars (KuCoin's cap
    per call) and date ranges are paged back from the newest bar.

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
        kucoin_interval = _INTERVAL_MAP.get(interval)
        if kucoin_interval is None:
            raise ProviderError(f"no {interval} bars")
        bar_sec = _BAR_SECONDS[interval]
        # KuCoin answers with the newest bars inside [startAt, endAt]: size the window to one page
        span = min(int(limit * 1.3 + 5), _PAGE) if limit else _PAGE
        kucoin_symbol = _normalise(symbol)

        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:

            async def page(before: int | None) -> list[Candle]:
                end_ts = int(time.time()) if before is None else before
                start_ts = end_ts - bar_sec * span
                if start is not None:
                    start_ts = max(start_ts, start)
                params = {
                    "symbol": kucoin_symbol,
                    "type": kucoin_interval,
                    "startAt": start_ts,
                    "endAt": end_ts,
                }
                async with session.get(_BASE_URL, params=params) as resp:
                    if resp.status != 200:
                        raise ProviderError(f"HTTP {resp.status}")
                    data = await resp.json()
                if data.get("code") != "200000":
                    raise ProviderError(f"API error {data.get('code')}: {data.get('msg', '')}")

                # KuCoin returns newest-first — reverse to get chronological order
                candles: list[Candle] = []
                for row in reversed(data.get("data") or []):
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
                return candles

            return await paginate(page, end=end, limit=limit, start=start)
