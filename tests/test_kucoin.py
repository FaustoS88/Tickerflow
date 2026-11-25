"""Tests for KuCoinProvider — HTTP answered by the local test server."""

from __future__ import annotations

import aiohttp
import pytest

from tests.upstream import Upstream
from tickerflow.errors import ProviderError
from tickerflow.models import Candle
from tickerflow.providers.kucoin import _BASE_URL, KuCoinProvider, _normalise

# KuCoin row format: [timestamp, open, close, high, low, volume, turnover]
_ROW = ["1700000000", "30000.0", "30200.5", "30500.0", "29800.0", "42.5", "1275000.0"]


@pytest.fixture()
def provider() -> KuCoinProvider:
    return KuCoinProvider()


def test_calls_the_real_endpoint_outside_tests() -> None:
    assert _BASE_URL == "https://api.kucoin.com/api/v1/market/candles"


# ---------------------------------------------------------------------------
# Symbol normalisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("BTCUSDT", "BTC-USDT"),
        ("ETHUSDT", "ETH-USDT"),
        ("SOLUSDT", "SOL-USDT"),
        ("ETHBTC",  "ETH-BTC"),
        ("BTCUSDC", "BTC-USDC"),
        ("btcusdt", "BTC-USDT"),
        ("BTC/USDT", "BTC-USDT"),
        ("BTC-USDT", "BTC-USDT"),
        ("XRPBNB",  "XRP-BNB"),
    ],
)
def test_normalise(symbol: str, expected: str) -> None:
    assert _normalise(symbol) == expected


# ---------------------------------------------------------------------------
# supports()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("BTCUSDT",  True),
        ("ETHUSDT",  True),
        ("SOLUSDT",  True),
        ("XRPUSDC",  True),
        ("ETHBTC",   True),
        ("AAPL",     False),   # stock — no known quote suffix
        ("WM.TO",    False),   # intl stock — has a dot
        ("EURUSD",   False),   # forex — no crypto quote suffix
        ("",         False),
    ],
)
def test_supports(provider: KuCoinProvider, symbol: str, expected: bool) -> None:
    assert provider.supports(symbol) is expected


# ---------------------------------------------------------------------------
# fetch() — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_returns_candles(provider: KuCoinProvider, upstream: Upstream) -> None:
    payload = {"code": "200000", "data": [_ROW]}

    upstream.reply("/kucoin", payload)
    result = await provider.fetch("BTCUSDT", "1d", 10)

    assert result is not None
    assert len(result) == 1
    candle = result[0]
    assert isinstance(candle, Candle)
    assert candle.time == 1_700_000_000
    assert candle.open == 30000.0
    assert candle.high == 30500.0
    assert candle.low == 29800.0
    assert candle.close == 30200.5
    assert candle.volume == 42.5


@pytest.mark.asyncio
async def test_fetch_reverses_order(provider: KuCoinProvider, upstream: Upstream) -> None:
    """KuCoin returns newest-first — provider must reverse to oldest-first."""
    rows = [
        [str(1_700_000_000 + (4 - i) * 86400), "100.0", "102.0", "105.0", "99.0", "10.0", "1000.0"]
        for i in range(5)
    ]
    payload = {"code": "200000", "data": rows}

    upstream.reply("/kucoin", payload)
    result = await provider.fetch("BTCUSDT", "1d", 5)

    assert result is not None
    assert result[0].time < result[-1].time


@pytest.mark.asyncio
async def test_fetch_respects_limit(provider: KuCoinProvider, upstream: Upstream) -> None:
    rows = [
        [str(1_700_000_000 + i * 86400), "100.0", "102.0", "105.0", "99.0", "10.0", "1000.0"]
        for i in range(20)
    ]
    # KuCoin returns newest-first, so reverse for realistic mock
    rows = list(reversed(rows))
    payload = {"code": "200000", "data": rows}

    upstream.reply("/kucoin", payload)
    result = await provider.fetch("BTCUSDT", "1d", 5)

    assert result is not None
    assert len(result) == 5


@pytest.mark.asyncio
async def test_fetch_all_intervals(provider: KuCoinProvider, upstream: Upstream) -> None:
    payload = {"code": "200000", "data": [_ROW]}

    for interval in ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"):
        upstream.reply("/kucoin", payload)
        result = await provider.fetch("BTCUSDT", interval, 1)
        assert result is not None, f"interval {interval} should return data"


@pytest.mark.asyncio
async def test_fetch_sends_kucoin_symbol_format(
    provider: KuCoinProvider, upstream: Upstream
) -> None:
    """Confirm the request uses BTC-USDT format, not BTCUSDT."""
    payload = {"code": "200000", "data": [_ROW]}

    upstream.reply("/kucoin", payload)
    await provider.fetch("BTCUSDT", "1d", 1)

    assert [query["symbol"] for _, query in upstream.requests] == ["BTC-USDT"]


# ---------------------------------------------------------------------------
# fetch() — error cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_raises_for_unsupported_interval(provider: KuCoinProvider) -> None:
    with pytest.raises(ProviderError, match="no 3d bars"):
        await provider.fetch("BTCUSDT", "3d", 10)


@pytest.mark.asyncio
async def test_fetch_raises_on_http_error(
    provider: KuCoinProvider, upstream: Upstream
) -> None:
    upstream.reply("/kucoin", status=429)
    with pytest.raises(ProviderError, match="HTTP 429"):
        await provider.fetch("BTCUSDT", "1d", 10)


@pytest.mark.asyncio
async def test_fetch_raises_with_the_api_error_code(
    provider: KuCoinProvider, upstream: Upstream
) -> None:
    payload = {"code": "400100", "msg": "Invalid symbol"}

    upstream.reply("/kucoin", payload)
    with pytest.raises(ProviderError, match="API error 400100: Invalid symbol"):
        await provider.fetch("BTCUSDT", "1d", 10)


@pytest.mark.asyncio
async def test_fetch_returns_none_on_empty_data(
    provider: KuCoinProvider, upstream: Upstream
) -> None:
    payload = {"code": "200000", "data": []}

    upstream.reply("/kucoin", payload)
    result = await provider.fetch("BTCUSDT", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_raises_on_network_error(
    provider: KuCoinProvider, upstream: Upstream
) -> None:
    upstream.reply("/kucoin", drop=True)
    with pytest.raises(aiohttp.ClientError):
        await provider.fetch("BTCUSDT", "1d", 10)


@pytest.mark.asyncio
async def test_fetch_skips_malformed_rows(provider: KuCoinProvider, upstream: Upstream) -> None:
    bad_row = ["1700000000"]  # too short
    payload = {"code": "200000", "data": [bad_row, _ROW]}

    upstream.reply("/kucoin", payload)
    result = await provider.fetch("BTCUSDT", "1d", 10)

    assert result is not None
    assert len(result) == 1
    assert result[0].open == 30000.0


@pytest.mark.asyncio
async def test_fetch_returns_none_when_all_rows_malformed(
    provider: KuCoinProvider, upstream: Upstream
) -> None:
    payload = {"code": "200000", "data": [["bad"], ["row"]]}

    upstream.reply("/kucoin", payload)
    result = await provider.fetch("BTCUSDT", "1d", 10)

    assert result is None
