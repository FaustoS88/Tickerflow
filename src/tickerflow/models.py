"""Data models for OHLCV candles."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Candle:
    """A single OHLCV bar.

    Attributes:
        time:   Unix timestamp (seconds, UTC).
        open:   Opening price.
        high:   Highest price during the bar.
        low:    Lowest price during the bar.
        close:  Closing price.
        volume: Traded volume (0 for instruments without volume data, e.g. forex).
    """

    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) must be >= low ({self.low})")
        if self.time <= 0:
            raise ValueError(f"time must be a positive unix timestamp, got {self.time}")


class Candles(list[Candle]):
    """Candles oldest first, with the name of the provider that served them."""

    def __init__(self, candles: Iterable[Candle] = (), provider: str = "") -> None:
        super().__init__(candles)
        self.provider = provider
