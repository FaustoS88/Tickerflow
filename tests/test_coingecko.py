"""Tests for CoinGeckoProvider — HTTP answered by the local test server."""

from __future__ import annotations

import pytest

from tests.upstream import Upstream
from tickerflow.errors import ProviderError
from tickerflow.models import Candle
from tickerflow.providers.coingecko import _BASE_URL, CoinGeckoProvider, _base_currency, _coin_id

# Sample OHLC row: [timestamp_ms, open, high, low, close]
_ROW = [1_700_000_000_000, 30000.0, 30500.0, 29800.0, 30200.5]


@pytest.fixture()
def provider() -> CoinGeckoProvider:
    return CoinGeckoProvider()


def test_calls_the_real_endpoint_outside_tests() -> None:
    assert _BASE_URL == "https://api.coingecko.com/api/v3"


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
async def test_fetch_returns_candles(provider: CoinGeckoProvider, upstream: Upstream) -> None:
    payload = [_ROW]

    upstream.reply("/coingecko/coins/bitcoin/ohlc", payload)
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
async def test_fetch_respects_limit(provider: CoinGeckoProvider, upstream: Upstream) -> None:
    rows = [[1_700_000_000_000 + i * 86_400_000, 100.0 + i, 105.0 + i, 99.0 + i, 102.0 + i]
            for i in range(10)]

    upstream.reply("/coingecko/coins/bitcoin/ohlc", rows)
    result = await provider.fetch("BTCUSDT", "4h", 3)

    assert result is not None
    assert len(result) == 3


@pytest.mark.asyncio
async def test_fetch_oldest_first(provider: CoinGeckoProvider, upstream: Upstream) -> None:
    rows = [[1_700_000_000_000 + i * 86_400_000, 100.0, 105.0, 99.0, 102.0]
            for i in range(5)]

    upstream.reply("/coingecko/coins/bitcoin/ohlc", rows)
    result = await provider.fetch("BTCUSDT", "4h", 5)

    assert result is not None
    assert result[0].time < result[-1].time


# ---------------------------------------------------------------------------
# fetch() — error cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("interval", ["1m", "1d"])  # daily bars need a paid CoinGecko plan
async def test_fetch_raises_for_unsupported_interval(
    provider: CoinGeckoProvider, interval: str
) -> None:
    with pytest.raises(ProviderError, match="serves 4h bars only"):
        await provider.fetch("BTCUSDT", interval, 10)


@pytest.mark.asyncio
async def test_fetch_leaves_more_than_180_bars_to_the_next_provider(
    provider: CoinGeckoProvider,
) -> None:
    with pytest.raises(ProviderError, match="at most 180 bars"):
        await provider.fetch("BTCUSDT", "4h", 181)


@pytest.mark.asyncio
async def test_fetch_raises_for_unknown_symbol(
    provider: CoinGeckoProvider,
) -> None:
    with pytest.raises(ProviderError, match="no coin id for XYZUSDT"):
        await provider.fetch("XYZUSDT", "4h", 10)


@pytest.mark.asyncio
async def test_fetch_raises_on_http_error(
    provider: CoinGeckoProvider, upstream: Upstream
) -> None:
    upstream.reply("/coingecko/coins/bitcoin/ohlc", {"error": "rate limit"}, status=429)
    with pytest.raises(ProviderError, match="HTTP 429"):
        await provider.fetch("BTCUSDT", "4h", 10)


@pytest.mark.asyncio
async def test_fetch_returns_none_on_empty_response(
    provider: CoinGeckoProvider, upstream: Upstream
) -> None:
    upstream.reply("/coingecko/coins/bitcoin/ohlc", [])
    result = await provider.fetch("BTCUSDT", "4h", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_4h_interval(provider: CoinGeckoProvider, upstream: Upstream) -> None:
    rows = [[1_700_000_000_000 + i * 14_400_000, 100.0, 105.0, 99.0, 102.0]
            for i in range(5)]

    upstream.reply("/coingecko/coins/ethereum/ohlc", rows)
    result = await provider.fetch("ETHUSDT", "4h", 5)

    assert result is not None
    assert len(result) == 5
