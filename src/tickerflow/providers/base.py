"""Abstract base class for all OHLCV providers."""

from __future__ import annotations

import datetime
import math
from abc import ABC, abstractmethod

import aiohttp

from tickerflow.models import Candle

#: One timeout for every aiohttp provider, so a silent upstream hands over to the next one fast.
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10)

#: Trading hours per day the window assumes: a US stock session.
_SESSION = datetime.timedelta(hours=6, minutes=30)


def market_window(bar: datetime.timedelta, limit: int) -> datetime.timedelta:
    """Calendar time that holds the last *limit* bars of a market open on weekdays only.

    Leaves room for weekends, holidays, half days, closures of up to a week and a
    session that has not opened yet today.
    """
    if bar >= datetime.timedelta(weeks=1):
        return bar * (limit + 2)
    market_days = math.ceil(limit / max(1, _SESSION // bar))
    return datetime.timedelta(days=market_days * 1.5 + 10)


class OHLCVProvider(ABC):
    """Base class every provider must implement.

    Providers are tried in order by the registry. The first one to return
    a non-empty list wins; the next provider is tried on None or empty.
    """

    #: Human-readable provider name used in logs and error messages.
    name: str = ""

    @abstractmethod
    def supports(self, symbol: str) -> bool:
        """Return True if this provider can attempt to fetch *symbol*.

        Implementations should do a quick pattern check (e.g. regex) and
        return False fast for symbols they definitely cannot handle.
        """

    @abstractmethod
    async def fetch(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> list[Candle] | None:
        """Fetch OHLCV candles for *symbol*.

        Args:
            symbol:   Normalised uppercase ticker (e.g. ``BTCUSDT``, ``AAPL``, ``EURUSD``).
            interval: Bar interval string — one of ``1m``, ``5m``, ``15m``,
                      ``1h``, ``4h``, ``1d``, ``1w``.
            limit:    Maximum number of bars to return (most-recent *limit* bars,
                      returned oldest-first).

        Returns:
            A list of :class:`~tickerflow.models.Candle` objects, oldest first,
            or ``None`` if the symbol is not available on this provider.
        """
