"""Tests for BinanceProvider — HTTP answered by the local test server."""

from __future__ import annotations

import pytest

from tests.upstream import Upstream
from tickerflow.errors import ProviderError
from tickerflow.models import Candle
from tickerflow.providers.binance import _KLINES_URL, BinanceProvider

# One kline row in Binance format: [open_time_ms, O, H, L, C, V, close_time_ms, ...]
_KLINE_ROW = [
    1_700_000_000_000,  # open time ms
    "30000.00",         # open
    "30500.00",         # high
    "29800.00",         # low
    "30200.50",         # close
    "123.45",           # volume
    1_700_086_399_999,  # close time ms
    "3711000.00",       # quote asset volume (ignored)
    42,                 # number of trades (ignored)
]


@pytest.fixture()
def provider() -> BinanceProvider:
    return BinanceProvider()


def test_calls_the_real_endpoint_outside_tests() -> None:
    assert _KLINES_URL == "https://api.binance.com/api/v3/klines"


# ---------------------------------------------------------------------------
# supports()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("BTCUSDT", True),
        ("ETHUSDT", True),
        ("SOLUSDC", True),
        ("ETHBTC", True),
        ("BNBUSDT", True),
        ("AAPL", False),
        ("EURUSD", False),
        ("WM.TO", False),
        ("", False),
    ],
)
def test_supports(provider: BinanceProvider, symbol: str, expected: bool) -> None:
    assert provider.supports(symbol) is expected


# ---------------------------------------------------------------------------
# fetch() — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_returns_candles(provider: BinanceProvider, upstream: Upstream) -> None:
    payload = [_KLINE_ROW]

    upstream.reply("/binance", payload)
    result = await provider.fetch("BTCUSDT", "1d", 1)

    assert result is not None
    assert len(result) == 1
    candle = result[0]
    assert isinstance(candle, Candle)
    assert candle.time == 1_700_000_000_000 // 1000
    assert candle.open == 30000.00
    assert candle.high == 30500.00
    assert candle.low == 29800.00
    assert candle.close == 30200.50
    assert candle.volume == 123.45


@pytest.mark.asyncio
async def test_fetch_multiple_candles(provider: BinanceProvider, upstream: Upstream) -> None:
    second_row = [
        1_700_086_400_000, "30200.50", "30800.00", "30100.00", "30700.00",
        "200.00", 1_700_172_799_999, "6140000.00", 88,
    ]
    payload = [_KLINE_ROW, second_row]

    upstream.reply("/binance", payload)
    result = await provider.fetch("BTCUSDT", "1d", 2)

    assert result is not None
    assert len(result) == 2
    assert result[0].time < result[1].time  # oldest-first


# ---------------------------------------------------------------------------
# fetch() — error cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_raises_with_the_status_on_http_error(
    provider: BinanceProvider, upstream: Upstream
) -> None:
    upstream.reply("/binance", {"code": -1121, "msg": "Invalid symbol."}, status=400)
    with pytest.raises(ProviderError, match="HTTP 400"):
        await provider.fetch("BTCUSDT", "1d", 10)


@pytest.mark.asyncio
async def test_fetch_returns_none_on_empty_response(
    provider: BinanceProvider, upstream: Upstream
) -> None:
    upstream.reply("/binance", [])
    result = await provider.fetch("BTCUSDT", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_raises_for_unsupported_interval(provider: BinanceProvider) -> None:
    # No HTTP call should be made — provider rejects the interval before fetching
    with pytest.raises(ProviderError, match="no 2d bars"):
        await provider.fetch("BTCUSDT", "2d", 10)


@pytest.mark.asyncio
async def test_fetch_raises_on_server_error(
    provider: BinanceProvider, upstream: Upstream
) -> None:
    upstream.reply("/binance", {}, status=500)
    with pytest.raises(ProviderError, match="HTTP 500"):
        await provider.fetch("BTCUSDT", "1d", 10)
