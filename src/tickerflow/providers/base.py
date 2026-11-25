"""Abstract base class for all OHLCV providers."""

from __future__ import annotations

import datetime
import math
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

import aiohttp

from tickerflow.errors import ProviderError
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


def utc(ts: int) -> str:
    """Unix seconds as a readable UTC time, for error messages."""
    return datetime.datetime.fromtimestamp(ts, datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")


async def paginate(
    page: Callable[[int | None], Awaitable[list[Candle]]],
    *,
    end: int | None = None,
    limit: int | None = None,
    start: int | None = None,
) -> list[Candle]:
    """Walk back in pages from *end* (inclusive, Unix seconds; None is now).

    ``page(end)`` returns the newest candles that open at or before *end*, oldest
    first. Stops at *limit* candles, once *start* is reached or on an empty page.
    """
    out: list[Candle] = []
    while True:
        # Bars after the end asked for mean the upstream ignored it: stop instead of looping
        batch = [c for c in await page(end) if end is None or c.time <= end]
        out[:0] = batch
        if not batch or (limit is not None and len(out) >= limit):
            return out
        end = batch[0].time - 1
        if start is not None and end < start:
            return out


class OHLCVProvider(ABC):
    """Base class every provider must implement.

    Providers are tried in order by the registry. The first one to return
    a non-empty list wins; the next provider is tried on None, empty or an
    exception, whose message becomes that provider's reason.
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
            or ``None`` if the provider has no bars for the symbol.

        Raises:
            ProviderError: the provider cannot serve the request; the message says why.
        """

    async def fetch_range(
        self,
        symbol: str,
        interval: str,
        start: int,
        end: int,
    ) -> list[Candle] | None:
        """Fetch the bars that open in ``[start, end)``, Unix seconds, oldest first.

        Providers that serve history override this; the others raise ProviderError.
        """
        raise ProviderError("does not serve date ranges")
