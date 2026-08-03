"""Tests for YFinanceProvider — mocked via patch on _download."""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pandas as pd
import pytest

from tickerflow.models import Candle
from tickerflow.providers.yfinance import YFinanceProvider, _to_yf_symbol


def _make_df(n: int = 5) -> pd.DataFrame:
    """Return a minimal DataFrame shaped like yf.Ticker().history()."""
    dates = pd.date_range(
        end=datetime.datetime.now(datetime.UTC),
        periods=n,
        freq="D",
        tz="UTC",
    )
    return pd.DataFrame(
        {
            "Open":   [100.0 + i for i in range(n)],
            "High":   [105.0 + i for i in range(n)],
            "Low":    [ 99.0 + i for i in range(n)],
            "Close":  [102.0 + i for i in range(n)],
            "Volume": [1_000_000.0] * n,
        },
        index=dates,
    )


@pytest.fixture()
def provider() -> YFinanceProvider:
    return YFinanceProvider()


# ---------------------------------------------------------------------------
# Symbol mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("BTCUSDT", "BTC-USD"),
        ("ETHUSDT", "ETH-USD"),
        ("SOLUSDC", "SOL-USD"),
        ("BNBUSDT", "BNB-USD"),
        ("ETHBTC",  "ETH-BTC"),   # coin-settled — keeps BTC quote
        ("EURUSD",  "EURUSD=X"),
        ("GBPJPY",  "GBPJPY=X"),
        ("AAPL",    "AAPL"),
        ("^GSPC",   "^GSPC"),
        ("WM.TO",   "WM.TO"),
        ("SPY",     "SPY"),
    ],
)
def test_to_yf_symbol(symbol: str, expected: str) -> None:
    assert _to_yf_symbol(symbol) == expected


# ---------------------------------------------------------------------------
# supports()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("BTCUSDT", True),
        ("EURUSD",  True),
        ("AAPL",    True),
        ("^GSPC",   True),
        ("WM.TO",   True),
        ("SPY",     True),
    ],
)
def test_supports(provider: YFinanceProvider, symbol: str, expected: bool) -> None:
    assert provider.supports(symbol) is expected


# ---------------------------------------------------------------------------
# fetch() — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_returns_candles(provider: YFinanceProvider) -> None:
    df = _make_df(5)
    with patch.object(YFinanceProvider, "_download", return_value=df):
        result = await provider.fetch("AAPL", "1d", 5)

    assert result is not None
    assert len(result) == 5
    candle = result[0]
    assert isinstance(candle, Candle)
    assert candle.open == 100.0
    assert candle.high == 105.0
    assert candle.low == 99.0
    assert candle.close == 102.0
    assert candle.volume == 1_000_000.0


@pytest.mark.asyncio
async def test_fetch_respects_limit(provider: YFinanceProvider) -> None:
    df = _make_df(10)
    with patch.object(YFinanceProvider, "_download", return_value=df):
        result = await provider.fetch("AAPL", "1d", 3)

    assert result is not None
    assert len(result) == 3


@pytest.mark.asyncio
async def test_fetch_oldest_first(provider: YFinanceProvider) -> None:
    df = _make_df(5)
    with patch.object(YFinanceProvider, "_download", return_value=df):
        result = await provider.fetch("AAPL", "1d", 5)

    assert result is not None
    assert result[0].time < result[-1].time


# ---------------------------------------------------------------------------
# fetch() — error cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_returns_none_for_unsupported_interval(provider: YFinanceProvider) -> None:
    result = await provider.fetch("AAPL", "4h", 10)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_when_download_fails(provider: YFinanceProvider) -> None:
    with patch.object(YFinanceProvider, "_download", return_value=None):
        result = await provider.fetch("AAPL", "1d", 10)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_empty_dataframe(provider: YFinanceProvider) -> None:
    empty_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    with patch.object(YFinanceProvider, "_download", return_value=empty_df):
        result = await provider.fetch("AAPL", "1d", 10)
    assert result is None
