"""tickerflow: async OHLCV market data from multiple free providers."""

from .models import Candle
from .registry import fetch

__all__ = ["Candle", "fetch"]
__version__ = "0.2.1"
