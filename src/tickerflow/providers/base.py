"""Abstract base class for all OHLCV providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tickerflow.models import Candle


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
