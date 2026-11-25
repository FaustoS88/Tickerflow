"""Tests for CoinGeckoProvider — mocked HTTP via aioresponses."""

from __future__ import annotations

import re

import pytest
from aioresponses import aioresponses

from tickerflow.models import Candle
from tickerflow.providers.coingecko import CoinGeckoProvider, _base_currency, _coin_id

_OHLC_RE = re.compile(r"https://api\.coingecko\.com/api/v3/coins/.*/ohlc.*")

# Sample OHLC row: [timestamp_ms, open, high, low, close]
_ROW = [1_700_000_000_000, 30000.0, 30500.0, 29800.0, 30200.5]


@pytest.fixture()
def provider() -> CoinGeckoProvider:
    return CoinGeckoProvider()


# ---------------------------------------------------------------------------
# Symbol helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("BTCUSDT", "BTC"),
        ("ETHUSDT", "ETH"),
        ("SOLUSDC", "SOL"),
        ("ETHBTC",  "ETH"),
        ("BNBUSDT", "BNB"),
        ("EURUSD",  None),   # not a crypto pair
        ("AAPL",    None),
    ],
)
def test_base_currency(symbol: str, expected: str | None) -> None:
    assert _base_currency(symbol) == expected


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("BTCUSDT", "bitcoin"),
        ("ETHUSDT", "ethereum"),
        ("SOLUSDC", "solana"),
        ("BNBUSDT", "binancecoin"),
        ("LINKUSDT", "chainlink"),
    ],
)
def test_coin_id(symbol: str, expected: str) -> None:
    assert _coin_id(symbol) == expected


# ---------------------------------------------------------------------------
# supports()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("BTCUSDT",  True),
        ("ETHUSDT",  True),
        ("SOLUSDC",  True),
        ("LINKUSDT", True),
        ("AAPL",     False),   # stock — not crypto
        ("EURUSD",   False),   # forex
        ("XYZUSDT",  False),   # unknown base currency
    ],
)
def test_supports(provider: CoinGeckoProvider, symbol: str, expected: bool) -> None:
    assert provider.supports(symbol) is expected


# ---------------------------------------------------------------------------
# fetch() — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_returns_candles(provider: CoinGeckoProvider) -> None:
    payload = [_ROW]

    with aioresponses() as mock:
        mock.get(_OHLC_RE, payload=payload, status=200)
        result = await provider.fetch("BTCUSDT", "4h", 10)

    assert result is not None
    assert len(result) == 1
    candle = result[0]
    assert isinstance(candle, Candle)
    assert candle.time == 1_700_000_000_000 // 1000 - 14_400  # close stamp → open time
    assert candle.open == 30000.0
    assert candle.high == 30500.0
    assert candle.low == 29800.0
    assert candle.close == 30200.5
    assert candle.volume == 0.0  # no volume in CoinGecko OHLC endpoint


@pytest.mark.asyncio
async def test_fetch_respects_limit(provider: CoinGeckoProvider) -> None:
    rows = [[1_700_000_000_000 + i * 86_400_000, 100.0 + i, 105.0 + i, 99.0 + i, 102.0 + i]
            for i in range(10)]

    with aioresponses() as mock:
        mock.get(_OHLC_RE, payload=rows, status=200)
        result = await provider.fetch("BTCUSDT", "4h", 3)

    assert result is not None
    assert len(result) == 3


@pytest.mark.asyncio
async def test_fetch_oldest_first(provider: CoinGeckoProvider) -> None:
    rows = [[1_700_000_000_000 + i * 86_400_000, 100.0, 105.0, 99.0, 102.0]
            for i in range(5)]

    with aioresponses() as mock:
        mock.get(_OHLC_RE, payload=rows, status=200)
        result = await provider.fetch("BTCUSDT", "4h", 5)

    assert result is not None
    assert result[0].time < result[-1].time


# ---------------------------------------------------------------------------
# fetch() — error cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("interval", ["1m", "1d"])  # daily bars need a paid CoinGecko plan
async def test_fetch_returns_none_for_unsupported_interval(
    provider: CoinGeckoProvider, interval: str
) -> None:
    result = await provider.fetch("BTCUSDT", interval, 10)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_leaves_more_than_180_bars_to_the_next_provider(
    provider: CoinGeckoProvider,
) -> None:
    assert await provider.fetch("BTCUSDT", "4h", 181) is None


@pytest.mark.asyncio
async def test_fetch_returns_none_for_unknown_symbol(
    provider: CoinGeckoProvider,
) -> None:
    result = await provider.fetch("XYZUSDT", "4h", 10)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_http_error(provider: CoinGeckoProvider) -> None:
    with aioresponses() as mock:
        mock.get(_OHLC_RE, status=429, payload={"error": "rate limit"})
        result = await provider.fetch("BTCUSDT", "4h", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_empty_response(
    provider: CoinGeckoProvider,
) -> None:
    with aioresponses() as mock:
        mock.get(_OHLC_RE, payload=[], status=200)
        result = await provider.fetch("BTCUSDT", "4h", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_4h_interval(provider: CoinGeckoProvider) -> None:
    rows = [[1_700_000_000_000 + i * 14_400_000, 100.0, 105.0, 99.0, 102.0]
            for i in range(5)]

    with aioresponses() as mock:
        mock.get(_OHLC_RE, payload=rows, status=200)
        result = await provider.fetch("ETHUSDT", "4h", 5)

    assert result is not None
    assert len(result) == 5
