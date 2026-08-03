"""Tests for TiingoProvider — mocked requests via unittest.mock."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from tickerflow.models import Candle
from tickerflow.providers.tiingo import TiingoProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(
    date: str = "2024-01-15T00:00:00+00:00",
    open_: float = 150.0,
    high: float = 155.0,
    low: float = 148.0,
    close: float = 153.0,
    volume: float = 1_000_000.0,
    adj: bool = True,
) -> dict:
    if adj:
        return {
            "date": date,
            "adjOpen": open_,
            "adjHigh": high,
            "adjLow": low,
            "adjClose": close,
            "adjVolume": volume,
        }
    return {
        "date": date,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


@pytest.fixture()
def provider() -> TiingoProvider:
    return TiingoProvider()


# ---------------------------------------------------------------------------
# supports()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("AAPL", True),
        ("TSLA", True),
        ("MSFT", True),
        ("SPY", True),
        ("A", True),
        ("GOOGL", True),
        ("WM.TO", True),      # Canadian exchange suffix
        ("RIO.L", True),      # London suffix
        ("BTCUSDT", False),   # crypto — too long for plain stock
        ("EURUSD", False),    # forex — 6 letters but no suffix
        ("BTC-USD", False),   # contains dash
        ("", False),
    ],
)
def test_supports(provider: TiingoProvider, symbol: str, expected: bool) -> None:
    assert provider.supports(symbol) is expected


# ---------------------------------------------------------------------------
# fetch() — interval guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_returns_none_for_intraday(provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")
    for interval in ("1m", "5m", "15m", "30m", "1h", "4h"):
        result = await provider.fetch("AAPL", interval, 10)
        assert result is None, f"Expected None for intraday interval {interval}"


@pytest.mark.asyncio
async def test_fetch_raises_without_api_key(provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TIINGO_API_KEY"):
        await provider.fetch("AAPL", "1d", 10)


# ---------------------------------------------------------------------------
# fetch() — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_daily_returns_candles(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")
    rows = [_make_row(f"2024-01-{15 + i:02d}T00:00:00+00:00") for i in range(5)]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = rows

    with patch("requests.get", return_value=mock_resp):
        result = await provider.fetch("AAPL", "1d", 5)

    assert result is not None
    assert len(result) == 5
    assert all(isinstance(c, Candle) for c in result)


@pytest.mark.asyncio
async def test_fetch_weekly_returns_candles(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")
    rows = [_make_row(f"2024-0{1 + i}-01T00:00:00+00:00") for i in range(3)]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = rows

    with patch("requests.get", return_value=mock_resp):
        result = await provider.fetch("SPY", "1w", 3)

    assert result is not None
    assert len(result) == 3


@pytest.mark.asyncio
async def test_fetch_uses_adj_fields_when_present(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")
    row = _make_row(open_=100.0, high=110.0, low=90.0, close=105.0, volume=500_000.0, adj=True)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [row]

    with patch("requests.get", return_value=mock_resp):
        result = await provider.fetch("AAPL", "1d", 1)

    assert result is not None
    c = result[0]
    assert c.open == 100.0
    assert c.high == 110.0
    assert c.low == 90.0
    assert c.close == 105.0
    assert c.volume == 500_000.0


@pytest.mark.asyncio
async def test_fetch_falls_back_to_unadj_fields(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")
    row = _make_row(open_=200.0, high=210.0, low=195.0, close=205.0, volume=250_000.0, adj=False)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [row]

    with patch("requests.get", return_value=mock_resp):
        result = await provider.fetch("MSFT", "1d", 1)

    assert result is not None
    assert result[0].open == 200.0
    assert result[0].close == 205.0


@pytest.mark.asyncio
async def test_fetch_respects_limit(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")
    rows = [_make_row(f"2024-01-{i + 1:02d}T00:00:00+00:00") for i in range(20)]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = rows

    with patch("requests.get", return_value=mock_resp):
        result = await provider.fetch("AAPL", "1d", 5)

    assert result is not None
    assert len(result) == 5


@pytest.mark.asyncio
async def test_fetch_symbol_uppercased_in_url(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [_make_row()]

    with patch("requests.get", return_value=mock_resp) as mock_get:
        await provider.fetch("aapl", "1d", 1)

    called_url = mock_get.call_args[0][0]
    assert "AAPL" in called_url
    assert "aapl" not in called_url


@pytest.mark.asyncio
async def test_fetch_passes_correct_resample_freq(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [_make_row()]

    with patch("requests.get", return_value=mock_resp) as mock_get:
        await provider.fetch("AAPL", "1w", 1)

    params = mock_get.call_args[1]["params"]
    assert params["resampleFreq"] == "weekly"


@pytest.mark.asyncio
async def test_fetch_passes_auth_header(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "my-secret-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [_make_row()]

    with patch("requests.get", return_value=mock_resp) as mock_get:
        await provider.fetch("AAPL", "1d", 1)

    headers = mock_get.call_args[1]["headers"]
    assert "Token my-secret-key" in headers["Authorization"]


# ---------------------------------------------------------------------------
# fetch() — error cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_returns_none_on_http_error(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("requests.get", return_value=mock_resp):
        result = await provider.fetch("AAPL", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_network_error(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")

    with patch("requests.get", side_effect=Exception("timeout")):
        result = await provider.fetch("AAPL", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_on_empty_response(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with patch("requests.get", return_value=mock_resp):
        result = await provider.fetch("AAPL", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_returns_none_when_api_returns_dict(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tiingo error responses return a dict, not a list — should return None."""
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"detail": "Not found."}

    with patch("requests.get", return_value=mock_resp):
        result = await provider.fetch("INVALID", "1d", 10)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_skips_malformed_rows(
    provider: TiingoProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")

    good = _make_row()
    bad = {"date": "not-a-date", "adjOpen": "oops"}

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [bad, good]

    with patch("requests.get", return_value=mock_resp):
        result = await provider.fetch("AAPL", "1d", 10)

    assert result is not None
    assert len(result) == 1


# ---------------------------------------------------------------------------
# _download() — unit tests (sync)
# ---------------------------------------------------------------------------

def test_download_returns_list_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_make_row()]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = rows

    with patch("requests.get", return_value=mock_resp):
        result = TiingoProvider._download(
            "AAPL",
            "daily",
            datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
            "key",
        )

    assert result == rows


def test_download_returns_none_on_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("requests.get", return_value=mock_resp):
        result = TiingoProvider._download(
            "AAPL",
            "daily",
            datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
            "key",
        )

    assert result is None


def test_download_returns_none_on_exception() -> None:
    with patch("requests.get", side_effect=ConnectionError("dns failure")):
        result = TiingoProvider._download(
            "AAPL",
            "daily",
            datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
            "key",
        )

    assert result is None
