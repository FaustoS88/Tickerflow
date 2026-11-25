"""yfinance OHLCV provider — stocks, ETFs, indices, crypto, and forex."""

from __future__ import annotations

import asyncio
import datetime
import re

import yfinance as yf

from tickerflow.errors import ProviderError
from tickerflow.models import Candle
from tickerflow.providers.base import OHLCVProvider, market_window

# tickerflow interval → yfinance interval
_INTERVAL_MAP: dict[str, str] = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "1h":  "1h",
    "1d":  "1d",
    "1w":  "1wk",
}

# How long each bar is — used to compute the download start date
_BAR_DURATION: dict[str, datetime.timedelta] = {
    "1m":  datetime.timedelta(minutes=1),
    "5m":  datetime.timedelta(minutes=5),
    "15m": datetime.timedelta(minutes=15),
    "1h":  datetime.timedelta(hours=1),
    "1d":  datetime.timedelta(days=1),
    "1w":  datetime.timedelta(weeks=1),
}

# Furthest look-back per intraday request, a day inside Yahoo's limits (yfinance history.py)
_MAX_LOOKBACK: dict[str, datetime.timedelta] = {
    "1m":  datetime.timedelta(days=7),
    "5m":  datetime.timedelta(days=59),
    "15m": datetime.timedelta(days=59),
    "1h":  datetime.timedelta(days=729),
}

_CRYPTO_RE    = re.compile(r"^[A-Z]{2,}(USDT|USDC|BTC|ETH|BNB|BUSD|FDUSD)$")
_FOREX_RE     = re.compile(r"^[A-Z]{6}$")
_STOCK_RE     = re.compile(r"^\^?[A-Z]{1,5}$")
_INTL_STOCK_RE = re.compile(r"^[A-Z0-9]{1,7}\.[A-Z]{1,3}$")


def _to_yf_symbol(symbol: str) -> str:
    """Map a normalised symbol to its yfinance ticker string.

    Rules:
    - Crypto  : strip quote currency, join with hyphen, USD-settle
                ``BTCUSDT`` → ``BTC-USD``, ``ETHBTC`` → ``ETH-BTC``
    - Forex   : append ``=X``  — ``EURUSD`` → ``EURUSD=X``
    - Stocks  : unchanged      — ``AAPL`` → ``AAPL``
    - Intl    : unchanged      — ``WM.TO`` → ``WM.TO``
    """
    up = symbol.upper()

    # Crypto — detect and strip known quote currencies
    for quote in ("USDT", "USDC", "BUSD", "FDUSD", "BNB", "ETH", "BTC"):
        if up.endswith(quote):
            base = up[: -len(quote)]
            # USD-settled stablecoins → -USD; coin-settled → keep quote ticker
            yf_quote = "USD" if quote in ("USDT", "USDC", "BUSD", "FDUSD") else quote
            return f"{base}-{yf_quote}"

    # Forex — yfinance expects the six-letter pair followed by =X
    if _FOREX_RE.match(up):
        return f"{up}=X"

    return up


class YFinanceProvider(OHLCVProvider):
    """Fetches OHLCV data via yfinance.

    Covers stocks, ETFs, indices (^GSPC), crypto (BTC-USD), and forex (EURUSD=X).
    yfinance is synchronous; blocking calls run in a thread pool so the async
    interface stays non-blocking.

    Note: 4h bars are not natively supported by yfinance and return None.
    """

    name = "yfinance"

    def supports(self, symbol: str) -> bool:
        up = symbol.upper()
        return bool(
            _CRYPTO_RE.match(up)
            or _FOREX_RE.match(up)
            or _STOCK_RE.match(up)
            or _INTL_STOCK_RE.match(up)
        )

    async def fetch(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> list[Candle] | None:
        yf_interval = _yf_interval(interval)
        window = market_window(_BAR_DURATION[interval], limit)
        window = min(window, _MAX_LOOKBACK.get(interval, window))
        start = datetime.datetime.now(datetime.UTC) - window

        df = await asyncio.to_thread(self._download, _to_yf_symbol(symbol), yf_interval, start)
        return _candles(df.tail(limit)) if df is not None else None

    async def fetch_range(
        self,
        symbol: str,
        interval: str,
        start: int,
        end: int,
    ) -> list[Candle] | None:
        yf_interval = _yf_interval(interval)
        begin = datetime.datetime.fromtimestamp(start, datetime.UTC)
        lookback = _MAX_LOOKBACK.get(interval)
        if lookback and datetime.datetime.now(datetime.UTC) - begin > lookback:
            raise ProviderError(f"Yahoo serves {interval} bars for the last {lookback.days} days")
        # An end in the future would stretch the request past Yahoo's intraday limits
        finish = min(datetime.datetime.fromtimestamp(end, datetime.UTC), datetime.datetime.now(datetime.UTC))
        df = await asyncio.to_thread(
            self._download, _to_yf_symbol(symbol), yf_interval, begin, finish
        )
        if df is None:
            return None
        return [c for c in _candles(df) or [] if start <= c.time < end] or None

    @staticmethod
    def _download(
        ticker: str,
        interval: str,
        start: datetime.datetime,
        end: datetime.datetime | None = None,
    ):
        """Blocking yfinance fetch — called via asyncio.to_thread."""
        df = yf.Ticker(ticker).history(start=start, end=end, interval=interval, auto_adjust=True)
        return df if not df.empty else None


def _yf_interval(interval: str) -> str:
    yf_interval = _INTERVAL_MAP.get(interval)
    if yf_interval is None:
        raise ProviderError(f"no {interval} bars")
    return yf_interval


def _candles(df) -> list[Candle] | None:
    candles: list[Candle] = []
    for ts, row in df.iterrows():
        try:
            candles.append(
                Candle(
                    time=int(ts.timestamp()),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume", 0.0) or 0.0),
                )
            )
        except (ValueError, KeyError):
            continue
    return candles or None
