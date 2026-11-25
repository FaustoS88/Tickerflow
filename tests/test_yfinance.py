"""Tests for YFinanceProvider — mocked via patch on _download."""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pandas as pd
import pytest

from tickerflow.errors import ProviderError
from tickerflow.models import Candle
from tickerflow.providers.base import market_window
from tickerflow.providers.yfinance import (
    _BAR_DURATION,
    YFinanceProvider,
    _to_yf_symbol,
)


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
async def test_fetch_raises_for_unsupported_interval(provider: YFinanceProvider) -> None:
    with pytest.raises(ProviderError, match="no 4h bars"):
        await provider.fetch("AAPL", "4h", 10)


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


# ---------------------------------------------------------------------------
# Download window
# ---------------------------------------------------------------------------

def _closed(day: datetime.date) -> bool:
    """Weekends, a holiday every 25 days and the 31 Dec to 3 Jan closure."""
    year_end = (day.month, day.day) == (12, 31) or (day.month == 1 and day.day <= 3)
    return day.weekday() >= 5 or day.toordinal() % 25 == 0 or year_end


def _bars(start: datetime.datetime, now: datetime.datetime, per_day: int) -> int:
    """Bars of the sessions opening (14:30 UTC) between *start* and *now*; a half day after
    each holiday."""
    total = 0
    for d in range((now - start).days + 2):
        opens = datetime.datetime.combine(start.date(), datetime.time(14, 30), datetime.UTC)
        opens += datetime.timedelta(days=d)
        day = opens.date()
        if start <= opens < now and not _closed(day):
            half = (day - datetime.timedelta(days=1)).toordinal() % 25 == 0
            total += max(1, per_day // 2) if half else per_day
    return total


@pytest.mark.parametrize("interval", ["1m", "5m", "15m", "1h", "1d", "1w"])
def test_window_holds_limit_bars_on_a_weekday_calendar(interval: str) -> None:
    bar = _BAR_DURATION[interval]
    per_day = max(1, datetime.timedelta(hours=6, minutes=30) // bar)
    monday = datetime.datetime(2026, 11, 2, 13, tzinfo=datetime.UTC)  # before the US open
    for limit in (1, per_day, 30, 100, 1000):
        window = market_window(bar, limit)
        if interval == "1w":
            assert window // bar >= limit
            continue
        for offset in range(84):  # through the year-end closure
            now = monday + datetime.timedelta(days=offset)
            assert _bars(now - window, now, per_day) >= limit, (limit, now)


@pytest.mark.asyncio
@pytest.mark.parametrize("interval", ["1m", "5m", "15m", "1h"])
async def test_intraday_window_stays_inside_yahoo_history(
    provider: YFinanceProvider, interval: str
) -> None:
    before = datetime.datetime.now(datetime.UTC)
    with patch.object(YFinanceProvider, "_download", return_value=None) as download:
        await provider.fetch("AAPL", interval, 5000)
    yahoo_days = {"1m": 8, "5m": 60, "15m": 60, "1h": 730}[interval]
    assert before - download.call_args.args[2] < datetime.timedelta(days=yahoo_days)
