"""Provider registry — auto-routes symbols to the right provider chain.

Asset class detection (rough rules, refined per provider):
- Crypto  : ends in USDT / USDC / BTC / ETH / BNB / BUSD  (e.g. BTCUSDT)
- Stocks  : 1-5 uppercase letters or starts with ^  (e.g. AAPL, ^GSPC)
- Intl    : TICKER.EXCHANGE  (e.g. WM.TO, OGC.AX, RIO.L)
- Forex   : exactly 6 uppercase letters  (e.g. EURUSD, GBPUSD)
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from tickerflow import cache
from tickerflow.errors import NoDataError
from tickerflow.models import Candle, Candles
from tickerflow.providers.base import OHLCVProvider

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)

# Lazy imports — providers are only loaded when first used
_binance: OHLCVProvider | None = None
_coingecko: OHLCVProvider | None = None
_kraken: OHLCVProvider | None = None
_kucoin: OHLCVProvider | None = None
_yfinance: OHLCVProvider | None = None
_tiingo: OHLCVProvider | None = None
_finnhub: OHLCVProvider | None = None

_CRYPTO_RE = re.compile(r"^[A-Z]{2,}(USDT|USDC|BTC|ETH|BNB|BUSD|FDUSD)$")
_STOCK_RE = re.compile(r"^\^?[A-Z]{1,5}$")
_INTL_STOCK_RE = re.compile(r"^[A-Z0-9]{1,7}\.[A-Z]{1,3}$")
_FOREX_RE = re.compile(r"^[A-Z]{6}$")

#: Every interval at least one provider serves; each provider says which of them it has
INTERVALS = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M")
_DEFAULT_LIMIT = 100


def _get_binance() -> OHLCVProvider:
    global _binance
    if _binance is None:
        from tickerflow.providers.binance import BinanceProvider
        _binance = BinanceProvider()
    return _binance


def _get_coingecko() -> OHLCVProvider:
    global _coingecko
    if _coingecko is None:
        from tickerflow.providers.coingecko import CoinGeckoProvider
        _coingecko = CoinGeckoProvider()
    return _coingecko


def _get_kraken() -> OHLCVProvider:
    global _kraken
    if _kraken is None:
        from tickerflow.providers.kraken import KrakenProvider
        _kraken = KrakenProvider()
    return _kraken


def _get_kucoin() -> OHLCVProvider:
    global _kucoin
    if _kucoin is None:
        from tickerflow.providers.kucoin import KuCoinProvider
        _kucoin = KuCoinProvider()
    return _kucoin


def _get_yfinance() -> OHLCVProvider:
    global _yfinance
    if _yfinance is None:
        from tickerflow.providers.yfinance import YFinanceProvider
        _yfinance = YFinanceProvider()
    return _yfinance


def _get_tiingo() -> OHLCVProvider:
    global _tiingo
    if _tiingo is None:
        from tickerflow.providers.tiingo import TiingoProvider
        _tiingo = TiingoProvider()
    return _tiingo


def _get_finnhub() -> OHLCVProvider:
    global _finnhub
    if _finnhub is None:
        from tickerflow.providers.finnhub import FinnhubProvider
        _finnhub = FinnhubProvider()
    return _finnhub


# Lazy factories — providers are constructed on demand
_FACTORIES = {
    "binance": _get_binance,
    "coingecko": _get_coingecko,
    "kraken": _get_kraken,
    "kucoin": _get_kucoin,
    "yfinance": _get_yfinance,
    "tiingo": _get_tiingo,
    "finnhub": _get_finnhub,
}


def pick(symbol: str) -> list[str]:
    """Return an ordered chain of provider names for *symbol* (no imports).

    Routing rules:
    - Crypto  → binance, coingecko, kraken, kucoin, yfinance
    - Stocks  → yfinance, tiingo, finnhub
    - Intl    → yfinance, finnhub
    - Forex   → yfinance, finnhub
    - Unknown → all providers
    """
    up = symbol.upper()

    if _CRYPTO_RE.match(up):
        return ["binance", "coingecko", "kraken", "kucoin", "yfinance"]

    if _STOCK_RE.match(up):
        return ["yfinance", "tiingo", "finnhub"]

    if _INTL_STOCK_RE.match(up):
        return ["yfinance", "finnhub"]

    if _FOREX_RE.match(up):
        return ["yfinance", "finnhub"]

    return ["binance", "coingecko", "kraken", "kucoin", "yfinance", "tiingo", "finnhub"]


def _candles_to_dataframe(candles: list[Candle]) -> pd.DataFrame:
    """Convert a list of Candle objects to a pandas DataFrame.

    Raises ImportError with an install hint if pandas is not available.
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError(
            "pandas is required for DataFrame output. "
            'Install it with: pip install "tickerflow[pandas]"'
        ) from None

    columns = ["time", "open", "high", "low", "close", "volume"]

    if not candles:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(
        [
            {
                "time": c.time,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
    )
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df


def _seconds(value: datetime.datetime | int, name: str) -> int:
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            raise ValueError(f"{name} must be timezone-aware, e.g. datetime(2025, 1, 1, tzinfo=UTC)")
        return int(value.timestamp())
    return int(value)


async def fetch(
    symbol: str,
    interval: str = "1d",
    limit: int | None = None,
    *,
    start: datetime.datetime | int | None = None,
    end: datetime.datetime | int | None = None,
    providers: Sequence[str] | None = None,
    timeout: float | None = 30.0,
) -> Candles:
    """Fetch OHLCV bars for *symbol*, trying providers in order until one serves them.

    Without *start*, returns the last *limit* bars (100 by default). With *start*,
    returns every bar that opens from *start* up to *end* (default: now); Binance,
    KuCoin, yfinance and Kraken (its last 720 bars only) serve date ranges.

    Args:
        symbol:    Ticker symbol (e.g. ``BTCUSDT``, ``AAPL``, ``EURUSD``, ``WM.TO``).
        interval:  Bar interval, one of :data:`INTERVALS` (``1m`` … ``1w``).
        limit:     Number of most recent bars; leave it out when passing *start*.
        start:     First bar's open time: a timezone-aware datetime or Unix seconds.
        end:       Bars must open before this time; needs *start*.
        providers: Provider names to try in this order, instead of the chain for the symbol.
        timeout:   Seconds for the whole chain, each provider's wait included; None for no limit.

    Returns:
        :class:`~tickerflow.models.Candles`, oldest first; ``.provider`` names who served them.

    Raises:
        NoDataError: no provider served the bars; ``.reasons`` says why, provider by provider.
        ValueError:  an argument is invalid (unknown interval or provider, limit below 1, …).
    """
    if interval not in INTERVALS:
        raise ValueError(f"interval {interval!r} is not one of {', '.join(INTERVALS)}")
    span: tuple[int, int] | None = None
    if start is None:
        if end is not None:
            raise ValueError("end needs start")
        limit = _DEFAULT_LIMIT if limit is None else limit
        if limit < 1:
            raise ValueError(f"limit must be at least 1, got {limit}")
    else:
        if limit is not None:
            raise ValueError("pass limit or start, not both")
        span = (_seconds(start, "start"), int(time.time()) if end is None else _seconds(end, "end"))
        if span[0] >= span[1]:
            raise ValueError("start must be before end")
    if providers is not None and (isinstance(providers, str) or not providers):
        raise ValueError("providers takes a non-empty list of provider names")
    chain = pick(symbol) if providers is None else list(providers)
    for name in chain:
        if name not in _FACTORIES:
            raise ValueError(f"unknown provider {name!r}, choose from {', '.join(_FACTORIES)}")

    use_cache = span is None and providers is None and cache.is_enabled()
    if use_cache and (hit := cache.get(symbol, interval, limit)) is not None:
        logger.debug("cache hit for %s %s (limit=%s)", symbol, interval, limit)
        return Candles(hit, provider=hit.provider)  # a copy: callers may change theirs

    loop = asyncio.get_running_loop()
    deadline = None if timeout is None else loop.time() + timeout
    reasons: dict[str, str] = {}
    for name in chain:
        try:
            provider = _FACTORIES[name]()
        except Exception as e:  # noqa: BLE001 — any import/init failure must fall back, not crash
            reasons[name] = f"unavailable: {e}"
            logger.warning("provider %s unavailable, skipping: %s", name, e)
            continue

        if not provider.supports(symbol):
            logger.debug("provider %s skipped — does not support %s", name, symbol)
            continue

        logger.debug("trying provider %s for %s %s", name, symbol, interval)
        budget = asyncio.timeout_at(deadline)
        try:
            async with budget:
                if span is None:
                    result = await provider.fetch(symbol, interval, limit)
                else:
                    result = await provider.fetch_range(symbol, interval, *span)
        except TimeoutError as e:
            if budget.expired():
                reasons[name] = f"stopped at the {timeout:g} s deadline"
                logger.warning("provider %s stopped at the deadline for %s %s", name, symbol, interval)
                break
            reasons[name] = str(e) or "timed out"
        except Exception as e:  # noqa: BLE001 — any provider error must fall back, not crash
            reasons[name] = str(e) or type(e).__name__
        else:
            if result:
                logger.debug(
                    "provider %s returned %d candles for %s %s", name, len(result), symbol, interval
                )
                served = Candles(result, provider=name)
                if use_cache:
                    cache.set(symbol, interval, limit, Candles(served, provider=name))
                return served
            reasons[name] = "no data"
        logger.warning("provider %s failed for %s %s: %s", name, symbol, interval, reasons[name])

    raise NoDataError(symbol, interval, reasons)


async def fetch_df(
    symbol: str,
    interval: str = "1d",
    limit: int | None = None,
    *,
    start: datetime.datetime | int | None = None,
    end: datetime.datetime | int | None = None,
    providers: Sequence[str] | None = None,
    timeout: float | None = 30.0,
) -> pd.DataFrame:
    """Like :func:`fetch`, as a ``pandas.DataFrame``; ``df.attrs["provider"]`` names who served it.

    Columns: ``time`` (UTC datetime), ``open``, ``high``, ``low``, ``close``, ``volume``.
    Requires ``pip install "tickerflow[pandas]"``.
    """
    candles = await fetch(
        symbol, interval, limit, start=start, end=end, providers=providers, timeout=timeout
    )
    df = _candles_to_dataframe(candles)
    df.attrs["provider"] = candles.provider
    return df


async def teardown() -> None:
    """Kept for compatibility: every provider closes its HTTP session after each request."""
