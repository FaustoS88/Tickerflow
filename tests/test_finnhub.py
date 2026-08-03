"""Tests for FinnhubProvider — mocked finnhub.Client via unittest.mock."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tickerflow.models import Candle
from tickerflow.providers.finnhub import FinnhubProvider, _to_forex_symbol

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candle_payload(n: int = 3, base_ts: int = 1_700_000_000) -> dict:
    """Build a minimal Finnhub-style candle response with n bars."""
    return {
        "s": "ok",
        "t": [base_ts + i * 86400 for i in range(n)],
        "o": [100.0 + i for i in range(n)],
        "h": [105.0 + i for i in range(n)],
        "l": [95.0 + i for i in range(n)],
        "c": [102.0 + i for i in range(n)],
        "v": [500_000.0 + i * 1000 for i in range(n)],
    }


@pytest.fixture()
def provider() -> FinnhubProvider:
    return FinnhubProvider()


# ---------------------------------------------------------------------------
# _to_forex_symbol()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("EURUSD", "OANDA:EUR_USD"),
        ("GBPJPY", "OANDA:GBP_JPY"),
        ("USDJPY", "OANDA:USD_JPY"),
        ("AUDUSD", "OANDA:AUD_USD"),
        ("USDCHF", "OANDA:USD_CHF"),
    ],
)
def test_to_forex_symbol(symbol: str, expected: str) -> None:
    assert _to_forex_symbol(symbol) == expected


# ---------------------------------------------------------------------------
# supports()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("AAPL", True),
        ("TSLA", True),
        ("^SPX", True),        # index
        ("RIO.L", True),       # London
        ("WM.TO", True),       # Toronto
        ("EURUSD", True),      # forex
        ("GBPUSD", True),      # forex
        ("BTCUSDT", False),    # 8 chars — crypto pair, too long for plain stock
        ("", False),
    ],
)
def test_supports(provider: FinnhubProvider, symbol: str, expected: bool) -> None:
    assert provider.supports(symbol) is expected


# ---------------------------------------------------------------------------
# fetch() — interval guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_returns_none_for_unsupported_interval(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    result = await provider.fetch("AAPL", "4h", 10)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_raises_without_api_key(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FINNHUB_API_KEY"):
        await provider.fetch("AAPL", "1d", 10)


# ---------------------------------------------------------------------------
# fetch() — stock happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_stock_returns_candles(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    payload = _candle_payload(5)

    mock_client = MagicMock()
    mock_client.stock_candles.return_value = payload

    with patch("finnhub.Client", return_value=mock_client):
        result = await provider.fetch("AAPL", "1d", 5)

    assert result is not None
    assert len(result) == 5
    assert all(isinstance(c, Candle) for c in result)


@pytest.mark.asyncio
async def test_fetch_stock_candle_values(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    payload = {
        "s": "ok",
        "t": [1_700_000_000],
        "o": [150.0],
        "h": [155.0],
        "l": [148.0],
        "c": [153.0],
        "v": [1_000_000.0],
    }

    mock_client = MagicMock()
    mock_client.stock_candles.return_value = payload

    with patch("finnhub.Client", return_value=mock_client):
        result = await provider.fetch("AAPL", "1d", 1)

    assert result is not None
    c = result[0]
    assert c.time == 1_700_000_000
    assert c.open == 150.0
    assert c.high == 155.0
    assert c.low == 148.0
    assert c.close == 153.0
    assert c.volume == 1_000_000.0


@pytest.mark.asyncio
async def test_fetch_stock_respects_limit(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    payload = _candle_payload(20)

    mock_client = MagicMock()
    mock_client.stock_candles.return_value = payload

    with patch("finnhub.Client", return_value=mock_client):
        result = await provider.fetch("AAPL", "1d", 7)

    assert result is not None
    assert len(result) == 7


@pytest.mark.asyncio
async def test_fetch_stock_multiple_intervals(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")

    for interval in ("1m", "5m", "15m", "30m", "1h", "1d", "1w"):
        payload = _candle_payload(1)
        mock_client = MagicMock()
        mock_client.stock_candles.return_value = payload

        with patch("finnhub.Client", return_value=mock_client):
            result = await provider.fetch("AAPL", interval, 1)

        assert result is not None, f"Expected candles for interval {interval}"


# ---------------------------------------------------------------------------
# fetch() — forex happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_forex_returns_candles(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    payload = _candle_payload(3)

    mock_client = MagicMock()
    mock_client.forex_candles.return_value = payload

    with patch("finnhub.Client", return_value=mock_client):
        result = await provider.fetch("EURUSD", "1h", 3)

    assert result is not None
    assert len(result) == 3


@pytest.mark.asyncio
async def test_fetch_forex_routes_to_oanda_format(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    payload = _candle_payload(1)

    mock_client = MagicMock()
    mock_client.forex_candles.return_value = payload

    with patch("finnhub.Client", return_value=mock_client):
        await provider.fetch("EURUSD", "1d", 1)

    call_args = mock_client.forex_candles.call_args[0]
    assert call_args[0] == "OANDA:EUR_USD"


@pytest.mark.asyncio
async def test_fetch_stock_not_routed_to_forex(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    payload = _candle_payload(1)

    mock_client = MagicMock()
    mock_client.stock_candles.return_value = payload

    with patch("finnhub.Client", return_value=mock_client):
        await provider.fetch("AAPL", "1d", 1)

    mock_client.stock_candles.assert_called_once()
    mock_client.forex_candles.assert_not_called()


# ---------------------------------------------------------------------------
# fetch() — error cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_returns_none_when_status_not_ok(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_client.stock_candles.return_value = {"s": "no_data"}

    with patch("finnhub.Client", return_value=mock_client):
        result = await provider.fetch("AAPL", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_client_exception(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_client.stock_candles.side_effect = Exception("API rate limit")

    with patch("finnhub.Client", return_value=mock_client):
        result = await provider.fetch("AAPL", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_forex_exception(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_client.forex_candles.side_effect = Exception("connection error")

    with patch("finnhub.Client", return_value=mock_client):
        result = await provider.fetch("EURUSD", "1h", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_none_response(
    provider: FinnhubProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_client.stock_candles.return_value = None

    with patch("finnhub.Client", return_value=mock_client):
        result = await provider.fetch("AAPL", "1d", 10)

    assert result is None


# ---------------------------------------------------------------------------
# _parse() — unit tests (sync)
# ---------------------------------------------------------------------------

def test_parse_returns_candles() -> None:
    payload = _candle_payload(3)
    result = FinnhubProvider._parse(payload, 10)

    assert result is not None
    assert len(result) == 3
    assert result[0].time == 1_700_000_000
    assert result[0].open == 100.0


def test_parse_returns_none_on_none_input() -> None:
    assert FinnhubProvider._parse(None, 10) is None


def test_parse_returns_none_on_empty_timestamps() -> None:
    payload = {"s": "ok", "t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    assert FinnhubProvider._parse(payload, 10) is None


def test_parse_respects_limit() -> None:
    payload = _candle_payload(10)
    result = FinnhubProvider._parse(payload, 4)
    assert result is not None
    assert len(result) == 4


def test_parse_handles_missing_volume() -> None:
    payload = {
        "s": "ok",
        "t": [1_700_000_000],
        "o": [100.0],
        "h": [105.0],
        "l": [95.0],
        "c": [102.0],
        # no "v" key
    }
    result = FinnhubProvider._parse(payload, 10)
    assert result is not None
    assert result[0].volume == 0.0


def test_parse_returns_most_recent_bars_on_limit() -> None:
    payload = _candle_payload(10, base_ts=1_700_000_000)
    result = FinnhubProvider._parse(payload, 3)
    assert result is not None
    # should be the last 3 bars (most recent timestamps)
    assert result[0].time == 1_700_000_000 + 7 * 86400
