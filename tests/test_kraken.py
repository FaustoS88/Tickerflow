"""Tests for KrakenProvider — mocked HTTP via aioresponses."""

from __future__ import annotations

import re

import pytest
from aioresponses import aioresponses

from tickerflow.models import Candle
from tickerflow.providers.kraken import KrakenProvider, _normalise

_OHLC_RE = re.compile(r"https://api\.kraken\.com/0/public/OHLC.*")

# Sample OHLC row: [timestamp, open, high, low, close, vwap, volume, count]
_ROW = [1_700_000_000, "30000.0", "30500.0", "29800.0", "30200.5", "30100.0", "42.5", 150]


@pytest.fixture()
def provider() -> KrakenProvider:
    return KrakenProvider()


# ---------------------------------------------------------------------------
# Symbol normalisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("BTCUSDT", "XBTUSDT"),
        ("ETHUSDT", "ETHUSDT"),
        ("btcusdt", "XBTUSDT"),
        ("BTC/USDT", "XBTUSDT"),
        ("SOLUSDT", "SOLUSDT"),
        ("BTCUSD", "XBTUSD"),
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
        ("BTCUSDT", True),
        ("ETHUSDT", True),
        ("SOLUSDT", True),
        ("SOLUSDC", True),
        ("ETHBTC", True),
        ("AAPL", False),      # stock
        ("WM.TO", False),     # intl stock
        ("EURUSD", False),    # forex, not crypto
    ],
)
def test_supports(provider: KrakenProvider, symbol: str, expected: bool) -> None:
    assert provider.supports(symbol) is expected


# ---------------------------------------------------------------------------
# fetch() — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_returns_candles(provider: KrakenProvider) -> None:
    payload = {"error": [], "result": {"XXBTUSDT": [_ROW], "last": 1_700_000_000}}

    with aioresponses() as mock:
        mock.get(_OHLC_RE, payload=payload, status=200)
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
async def test_fetch_respects_limit(provider: KrakenProvider) -> None:
    rows = [
        [1_700_000_000 + i * 86400, "100.0", "105.0", "99.0", "102.0", "101.0", "10.0", 50]
        for i in range(10)
    ]
    payload = {"error": [], "result": {"XXBTUSDT": rows, "last": 0}}

    with aioresponses() as mock:
        mock.get(_OHLC_RE, payload=payload, status=200)
        result = await provider.fetch("BTCUSDT", "1d", 3)

    assert result is not None
    assert len(result) == 3


@pytest.mark.asyncio
async def test_fetch_oldest_first(provider: KrakenProvider) -> None:
    rows = [
        [1_700_000_000 + i * 86400, "100.0", "105.0", "99.0", "102.0", "101.0", "10.0", 50]
        for i in range(5)
    ]
    payload = {"error": [], "result": {"XETHUSDT": rows, "last": 0}}

    with aioresponses() as mock:
        mock.get(_OHLC_RE, payload=payload, status=200)
        result = await provider.fetch("ETHUSDT", "1d", 5)

    assert result is not None
    assert result[0].time < result[-1].time


@pytest.mark.asyncio
async def test_fetch_multiple_intervals(provider: KrakenProvider) -> None:
    row = [1_700_000_000, "100.0", "105.0", "99.0", "102.0", "101.0", "10.0", 50]

    for interval in ("1m", "5m", "15m", "1h", "4h", "1d", "1w"):
        payload = {"error": [], "result": {"XXBTUSDT": [row], "last": 0}}
        with aioresponses() as mock:
            mock.get(_OHLC_RE, payload=payload, status=200)
            result = await provider.fetch("BTCUSDT", interval, 1)
        assert result is not None, f"interval {interval} should return data"


# ---------------------------------------------------------------------------
# fetch() — error cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_returns_none_for_unsupported_interval(
    provider: KrakenProvider,
) -> None:
    result = await provider.fetch("BTCUSDT", "3d", 10)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_http_error(provider: KrakenProvider) -> None:
    with aioresponses() as mock:
        mock.get(_OHLC_RE, status=500)
        result = await provider.fetch("BTCUSDT", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_api_error(provider: KrakenProvider) -> None:
    payload = {"error": ["EQuery:Unknown asset pair"], "result": {}}

    with aioresponses() as mock:
        mock.get(_OHLC_RE, payload=payload, status=200)
        result = await provider.fetch("BTCUSDT", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_empty_result(provider: KrakenProvider) -> None:
    payload = {"error": [], "result": {"XXBTUSDT": [], "last": 0}}

    with aioresponses() as mock:
        mock.get(_OHLC_RE, payload=payload, status=200)
        result = await provider.fetch("BTCUSDT", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_network_error(provider: KrakenProvider) -> None:
    with aioresponses() as mock:
        mock.get(_OHLC_RE, exception=Exception("connection timeout"))
        result = await provider.fetch("BTCUSDT", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_handles_missing_result_key(provider: KrakenProvider) -> None:
    payload = {"error": [], "result": {"last": 0}}

    with aioresponses() as mock:
        mock.get(_OHLC_RE, payload=payload, status=200)
        result = await provider.fetch("BTCUSDT", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_skips_malformed_rows(provider: KrakenProvider) -> None:
    """Rows missing fields should be skipped, valid rows still returned."""
    good_row = [1_700_000_000, "100.0", "105.0", "99.0", "102.0", "101.0", "10.0", 50]
    bad_row = [1_700_000_000, "oops"]  # missing fields
    payload = {"error": [], "result": {"XXBTUSDT": [bad_row, good_row], "last": 0}}

    with aioresponses() as mock:
        mock.get(_OHLC_RE, payload=payload, status=200)
        result = await provider.fetch("BTCUSDT", "1d", 10)

    assert result is not None
    assert len(result) == 1
    assert result[0].open == 100.0
