"""Provider registry — auto-routes symbols to the right provider chain.

Asset class detection (rough rules, refined per provider):
- Crypto  : ends in USDT / USDC / BTC / ETH / BNB / BUSD  (e.g. BTCUSDT)
- Stocks  : 1–5 uppercase letters or starts with ^  (e.g. AAPL, ^GSPC)
- Intl    : TICKER.EXCHANGE  (e.g. WM.TO, OGC.AX, RIO.L)
- Forex   : exactly 6 uppercase letters  (e.g. EURUSD, GBPUSD)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from tickerflow import cache
from tickerflow.models import Candle
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
_STOCK_RE = re.compile(r"^(\^[A-Z]+|[A-Z]{1,5})$")
_INTL_STOCK_RE = re.compile(r"^[A-Z0-9]{1,7}\.[A-Z]{1,3}$")
_FOREX_RE = re.compile(r"^[A-Z]{6}$")


def _get_binance() -> OHLCVProvider:
    global _binance
    if _binance is None:
        from tickerflow.providers.binance import BinanceProvider  # noqa: PLC0415
        _binance = BinanceProvider()
    return _binance


def _get_coingecko() -> OHLCVProvider:
    global _coingecko
    if _coingecko is None:
        from tickerflow.providers.coingecko import CoinGeckoProvider  # noqa: PLC0415
        _coingecko = CoinGeckoProvider()
    return _coingecko


def _get_kraken() -> OHLCVProvider:
    global _kraken
    if _kraken is None:
        from tickerflow.providers.kraken import KrakenProvider  # noqa: PLC0415
        _kraken = KrakenProvider()
    return _kraken


def _get_kucoin() -> OHLCVProvider:
    global _kucoin
    if _kucoin is None:
        from tickerflow.providers.kucoin import KuCoinProvider  # noqa: PLC0415
        _kucoin = KuCoinProvider()
    return _kucoin


def _get_yfinance() -> OHLCVProvider:
    global _yfinance
    if _yfinance is None:
        from tickerflow.providers.yfinance import YFinanceProvider  # noqa: PLC0415
        _yfinance = YFinanceProvider()
    return _yfinance


def _get_tiingo() -> OHLCVProvider:
    global _tiingo
    if _tiingo is None:
        from tickerflow.providers.tiingo import TiingoProvider  # noqa: PLC0415
        _tiingo = TiingoProvider()
    return _tiingo


def _get_finnhub() -> OHLCVProvider:
    global _finnhub
    if _finnhub is None:
        from tickerflow.providers.finnhub import FinnhubProvider  # noqa: PLC0415
        _finnhub = FinnhubProvider()
    return _finnhub


def pick(symbol: str) -> list[OHLCVProvider]:
    """Return an ordered provider chain for *symbol*.

    Routing rules:
    - Crypto  → Binance (primary), yfinance (fallback)
    - Stocks  → yfinance (primary), Tiingo (fallback daily/weekly only),
                Finnhub (fallback for intraday)
    - Intl    → yfinance (primary), Finnhub (fallback)
    - Forex   → yfinance (primary), Finnhub (fallback)
    - Unknown → all providers
    """
    up = symbol.upper()

    if _CRYPTO_RE.match(up):
        return [_get_binance(), _get_coingecko(), _get_kraken(), _get_kucoin(), _get_yfinance()]

    if _STOCK_RE.match(up):
        # Tiingo covers daily/weekly; Finnhub covers intraday — both tried as fallbacks
        return [_get_yfinance(), _get_tiingo(), _get_finnhub()]

    if _INTL_STOCK_RE.match(up):
        return [_get_yfinance(), _get_finnhub()]

    if _FOREX_RE.match(up):
        return [_get_yfinance(), _get_finnhub()]

    # Unknown — try all
    return [_get_binance(), _get_coingecko(), _get_kraken(), _get_kucoin(), _get_yfinance(), _get_tiingo(), _get_finnhub()]


def _candles_to_dataframe(candles: list[Candle]) -> "pd.DataFrame":
    """Convert a list of Candle objects to a pandas DataFrame.

    Raises ImportError with an install hint if pandas is not available.
    """
    try:
        import pandas as pd  # noqa: PLC0415
    except ImportError:
        raise ImportError(
            "pandas is required for DataFrame output. "
            "Install it with: pip install tickerflow[pandas]"
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


async def fetch(
    symbol: str,
    interval: str = "1d",
    limit: int = 100,
    *,
    as_dataframe: bool = False,
) -> "list[Candle] | pd.DataFrame | None":
    """Fetch OHLCV data for *symbol*, trying providers in order.

    Returns the first successful result, or ``None`` if all providers fail.

    Args:
        symbol:       Ticker symbol (e.g. ``BTCUSDT``, ``AAPL``, ``EURUSD``, ``WM.TO``).
        interval:     Bar interval — ``1m``, ``5m``, ``15m``, ``1h``, ``4h``, ``1d``, ``1w``.
        limit:        Number of bars to return (most recent, oldest-first).
        as_dataframe: If True, return a ``pandas.DataFrame`` instead of a list of
                      :class:`~tickerflow.models.Candle` objects. Requires
                      ``pip install tickerflow[pandas]``.
    """
    if cache.is_enabled():
        cached = cache.get(symbol, interval, limit)
        if cached is not None:
            logger.debug("cache hit for %s %s (limit=%d)", symbol, interval, limit)
            return _candles_to_dataframe(cached) if as_dataframe else cached

    chain = pick(symbol)
    tried: list[str] = []

    for provider in chain:
        if not provider.supports(symbol):
            logger.debug("provider %s skipped — does not support %s", provider.name, symbol)
            continue

        logger.debug("trying provider %s for %s %s", provider.name, symbol, interval)
        result = await provider.fetch(symbol, interval, limit)

        if result:
            logger.debug(
                "provider %s returned %d candles for %s %s",
                provider.name,
                len(result),
                symbol,
                interval,
            )
            if cache.is_enabled():
                cache.set(symbol, interval, limit, result)
            return _candles_to_dataframe(result) if as_dataframe else result

        tried.append(provider.name)
        logger.warning(
            "provider %s returned no data for %s %s", provider.name, symbol, interval
        )

    logger.error(
        "all providers failed for %s %s — tried: %s",
        symbol,
        interval,
        tried or ["none"],
    )
    return None


async def teardown() -> None:
    """Close any open provider sessions (e.g. aiohttp).

    Call this before the event loop exits to avoid 'Unclosed client session'
    warnings at process shutdown.
    """
    from tickerflow.providers import binance as _bm  # noqa: PLC0415

    if _bm._session is not None and not _bm._session.closed:
        await _bm._session.close()
