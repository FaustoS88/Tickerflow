"""Provider registry — auto-routes symbols to the right provider chain.

Asset class detection (rough rules, refined per provider):
- Crypto  : ends in USDT / USDC / BTC / ETH / BNB / BUSD  (e.g. BTCUSDT)
- Stocks  : 1-5 uppercase letters or starts with ^  (e.g. AAPL, ^GSPC)
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
_STOCK_RE = re.compile(r"^\^?[A-Z]{1,5}$")
_INTL_STOCK_RE = re.compile(r"^[A-Z0-9]{1,7}\.[A-Z]{1,3}$")
_FOREX_RE = re.compile(r"^[A-Z]{6}$")


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


async def fetch(
    symbol: str,
    interval: str = "1d",
    limit: int = 100,
    *,
    as_dataframe: bool = False,
) -> list[Candle] | pd.DataFrame | None:
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

    tried: list[str] = []

    for name in pick(symbol):
        if not isinstance(name, str):
            provider = name
            name_str = getattr(provider, "name", str(provider))
        else:
            name_str = name
            if name not in _FACTORIES:
                logger.warning("provider %s unavailable, skipping", name)
                tried.append(name)
                continue
            try:
                provider = _FACTORIES[name]()
            except Exception as e:  # noqa: BLE001 — any import/init failure must fall back, not crash
                logger.warning("provider %s unavailable, skipping: %s", name, e)
                tried.append(name)
                continue

        if not provider.supports(symbol):
            logger.debug("provider %s skipped — does not support %s", name_str, symbol)
            continue

        logger.debug("trying provider %s for %s %s", name_str, symbol, interval)
        try:
            result = await provider.fetch(symbol, interval, limit)
        except Exception as e:  # noqa: BLE001 — any provider error must fall back, not crash
            logger.warning("provider %s raised, falling back: %s", name_str, e)
            tried.append(name_str)
            continue

        if result:
            logger.debug(
                "provider %s returned %d candles for %s %s",
                name_str,
                len(result),
                symbol,
                interval,
            )
            if cache.is_enabled():
                cache.set(symbol, interval, limit, result)
            return _candles_to_dataframe(result) if as_dataframe else result

        tried.append(name_str)
        logger.warning(
            "provider %s returned no data for %s %s", name_str, symbol, interval
        )

    logger.error(
        "all providers failed for %s %s — tried: %s",
        symbol,
        interval,
        tried or ["none"],
    )
    return None


async def teardown() -> None:
    """Close open provider sessions (e.g. aiohttp).

    Only touches providers that were actually instantiated, so a crypto-only
    run never imports yfinance at process shutdown.
    """
    import importlib

    _instances = [
        (_binance, "tickerflow.providers.binance"),
        (_coingecko, "tickerflow.providers.coingecko"),
        (_kraken, "tickerflow.providers.kraken"),
        (_kucoin, "tickerflow.providers.kucoin"),
        (_yfinance, "tickerflow.providers.yfinance"),
        (_tiingo, "tickerflow.providers.tiingo"),
        (_finnhub, "tickerflow.providers.finnhub"),
    ]
    for instance, mod_path in _instances:
        if instance is None:
            continue
        mod = importlib.import_module(mod_path)
        session = getattr(mod, "_session", None)
        if session is not None and not session.closed:
            await session.close()
