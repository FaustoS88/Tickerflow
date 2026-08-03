"""Finnhub OHLCV provider — stock candles and forex quotes.

Requires a free Finnhub API key: https://finnhub.io/dashboard
Set the ``FINNHUB_API_KEY`` environment variable before use.

Install the optional dep before use:
    pip install "tickerflow[finnhub]"
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time

from tickerflow.models import Candle
from tickerflow.providers.base import OHLCVProvider

logger = logging.getLogger(__name__)

# Finnhub resolution strings
_RESOLUTION_MAP: dict[str, str] = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "1d": "D",
    "1w": "W",
}

# Approximate bar duration in seconds — used to compute the from-timestamp
_BAR_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3_600,
    "1d": 86_400,
    "1w": 604_800,
}

_STOCK_RE = re.compile(r"^(\^[A-Z]+|[A-Z]{1,5})$")
_INTL_STOCK_RE = re.compile(r"^[A-Z0-9]{1,7}\.[A-Z]{1,3}$")
_FOREX_RE = re.compile(r"^[A-Z]{6}$")


def _to_forex_symbol(symbol: str) -> str:
    """Convert a 6-letter forex pair to Finnhub's OANDA format.

    Examples:
        ``EURUSD`` → ``OANDA:EUR_USD``
        ``GBPJPY`` → ``OANDA:GBP_JPY``
    """
    return f"OANDA:{symbol[:3]}_{symbol[3:]}"


class FinnhubProvider(OHLCVProvider):
    """Fetches OHLCV candles from Finnhub for US stocks and forex pairs.

    Supports:
    - US stocks and indices — ``AAPL``, ``TSLA``, ``^SPX``
    - International stocks (exchange-suffixed) — ``RIO.L``, ``WM.TO``
    - Forex pairs — ``EURUSD``, ``GBPUSD``

    The ``4h`` interval is not offered by Finnhub and returns ``None``.

    Requires the ``finnhub-python`` package (``pip install "tickerflow[finnhub]"``)
    and a free API key from https://finnhub.io/dashboard set as
    ``FINNHUB_API_KEY``.
    """

    name = "finnhub"

    def supports(self, symbol: str) -> bool:
        up = symbol.upper()
        return bool(
            _STOCK_RE.match(up)
            or _INTL_STOCK_RE.match(up)
            or _FOREX_RE.match(up)
        )

    async def fetch(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> list[Candle] | None:
        resolution = _RESOLUTION_MAP.get(interval)
        if resolution is None:
            # 4h and other unmapped intervals are not supported
            return None

        api_key = os.getenv("FINNHUB_API_KEY")
        if not api_key:
            raise RuntimeError(
                "FINNHUB_API_KEY environment variable is not set. "
                "Get a free key at https://finnhub.io/dashboard"
            )

        bar_sec = _BAR_SECONDS[interval]
        to_ts = int(time.time())
        from_ts = to_ts - bar_sec * int(limit * 1.3 + 5)

        up = symbol.upper()
        if _FOREX_RE.match(up):
            raw = await asyncio.to_thread(
                self._fetch_forex, up, resolution, from_ts, to_ts, api_key
            )
        else:
            raw = await asyncio.to_thread(
                self._fetch_stock, up, resolution, from_ts, to_ts, api_key
            )

        return self._parse(raw, limit)

    # ------------------------------------------------------------------
    # Private helpers (blocking — called via asyncio.to_thread)
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_stock(
        symbol: str,
        resolution: str,
        from_ts: int,
        to_ts: int,
        api_key: str,
    ) -> dict | None:
        try:
            import finnhub

            data = finnhub.Client(api_key=api_key).stock_candles(
                symbol, resolution, from_ts, to_ts
            )
            if data and data.get("s") != "ok":
                logger.warning(
                    "finnhub stock_candles status=%s for %s", data.get("s"), symbol
                )
            return data if data and data.get("s") == "ok" else None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "finnhub stock_candles raised %s: %s", type(exc).__name__, exc
            )
            return None

    @staticmethod
    def _fetch_forex(
        symbol: str,
        resolution: str,
        from_ts: int,
        to_ts: int,
        api_key: str,
    ) -> dict | None:
        try:
            import finnhub

            fx_sym = _to_forex_symbol(symbol)
            data = finnhub.Client(api_key=api_key).forex_candles(
                fx_sym, resolution, from_ts, to_ts
            )
            if data and data.get("s") != "ok":
                logger.warning(
                    "finnhub forex_candles status=%s for %s", data.get("s"), fx_sym
                )
            return data if data and data.get("s") == "ok" else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("finnhub forex_candles raised %s: %s", type(exc).__name__, exc)
            return None

    @staticmethod
    def _parse(raw: dict | None, limit: int) -> list[Candle] | None:
        """Convert a Finnhub candle response dict into a Candle list."""
        if not raw:
            return None

        timestamps = raw.get("t", [])
        opens = raw.get("o", [])
        highs = raw.get("h", [])
        lows = raw.get("l", [])
        closes = raw.get("c", [])
        volumes = raw.get("v", [0.0] * len(timestamps))

        candles: list[Candle] = []
        for i in range(len(timestamps)):
            try:
                candles.append(
                    Candle(
                        time=int(timestamps[i]),
                        open=float(opens[i]),
                        high=float(highs[i]),
                        low=float(lows[i]),
                        close=float(closes[i]),
                        volume=float(volumes[i]) if i < len(volumes) else 0.0,
                    )
                )
            except (IndexError, KeyError, ValueError):
                continue

        return candles[-limit:] or None
