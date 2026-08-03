"""Tests for the TTL cache module and its integration with registry.fetch()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tickerflow import cache
from tickerflow.models import Candle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candles(n: int = 3) -> list[Candle]:
    return [
        Candle(
            time=1_700_000_000 + i * 86400,
            open=100.0,
            high=105.0,
            low=95.0,
            close=102.0,
            volume=1000.0,
        )
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def reset_cache():
    """Ensure each test starts with an empty cache."""
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# ttl_for()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "interval,expected",
    [
        ("1m",  30),
        ("5m",  120),
        ("15m", 300),
        ("30m", 600),
        ("1h",  1_800),
        ("4h",  7_200),
        ("1d",  14_400),
        ("1w",  86_400),
        ("3d",  60),   # unmapped — falls back to default
    ],
)
def test_ttl_for(interval: str, expected: int) -> None:
    assert cache.ttl_for(interval) == expected


# ---------------------------------------------------------------------------
# get / set / clear
# ---------------------------------------------------------------------------

def test_get_returns_none_on_empty_cache() -> None:
    assert cache.get("BTCUSDT", "1d", 10) is None


def test_set_and_get_returns_candles() -> None:
    candles = _candles(5)
    cache.set("BTCUSDT", "1d", 5, candles)
    result = cache.get("BTCUSDT", "1d", 5)
    assert result is candles


def test_get_is_case_insensitive_on_symbol() -> None:
    candles = _candles(3)
    cache.set("btcusdt", "1d", 3, candles)
    assert cache.get("BTCUSDT", "1d", 3) is candles
    assert cache.get("btcusdt", "1d", 3) is candles


def test_different_limits_are_separate_entries() -> None:
    a = _candles(5)
    b = _candles(10)
    cache.set("BTCUSDT", "1d", 5, a)
    cache.set("BTCUSDT", "1d", 10, b)
    assert cache.get("BTCUSDT", "1d", 5) is a
    assert cache.get("BTCUSDT", "1d", 10) is b


def test_different_intervals_are_separate_entries() -> None:
    hourly = _candles(2)
    daily = _candles(3)
    cache.set("AAPL", "1h", 2, hourly)
    cache.set("AAPL", "1d", 3, daily)
    assert cache.get("AAPL", "1h", 2) is hourly
    assert cache.get("AAPL", "1d", 3) is daily


def test_different_symbols_are_separate_entries() -> None:
    btc = _candles(2)
    eth = _candles(2)
    cache.set("BTCUSDT", "1d", 2, btc)
    cache.set("ETHUSDT", "1d", 2, eth)
    assert cache.get("BTCUSDT", "1d", 2) is btc
    assert cache.get("ETHUSDT", "1d", 2) is eth


def test_clear_removes_all_entries() -> None:
    cache.set("BTCUSDT", "1d", 10, _candles())
    cache.set("AAPL", "1h", 5, _candles())
    cache.clear()
    assert cache.size() == 0
    assert cache.get("BTCUSDT", "1d", 10) is None


def test_size_tracks_entries() -> None:
    assert cache.size() == 0
    cache.set("BTCUSDT", "1d", 10, _candles())
    assert cache.size() == 1
    cache.set("AAPL", "1d", 5, _candles())
    assert cache.size() == 2


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------

def test_expired_entry_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    candles = _candles(3)
    cache.set("BTCUSDT", "1m", 3, candles)  # TTL = 30s

    # Advance monotonic clock past expiry
    import time
    original = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original() + 31)

    assert cache.get("BTCUSDT", "1m", 3) is None


def test_expired_entry_is_evicted(monkeypatch: pytest.MonkeyPatch) -> None:
    cache.set("BTCUSDT", "1m", 3, _candles())
    assert cache.size() == 1

    import time
    original = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original() + 31)

    cache.get("BTCUSDT", "1m", 3)  # triggers eviction
    assert cache.size() == 0


def test_non_expired_entry_still_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    candles = _candles(3)
    cache.set("BTCUSDT", "1d", 3, candles)  # TTL = 14400s

    import time
    original = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original() + 100)

    assert cache.get("BTCUSDT", "1d", 3) is candles


# ---------------------------------------------------------------------------
# is_enabled()
# ---------------------------------------------------------------------------

def test_cache_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OHLCV_CACHE_ENABLED", raising=False)
    assert cache.is_enabled() is True


def test_cache_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OHLCV_CACHE_ENABLED", "false")
    assert cache.is_enabled() is False


def test_cache_enabled_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OHLCV_CACHE_ENABLED", "true")
    assert cache.is_enabled() is True


# ---------------------------------------------------------------------------
# registry.fetch() integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_registry_fetch_populates_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OHLCV_CACHE_ENABLED", raising=False)
    candles = _candles(5)

    from tickerflow import registry
    mock_provider = MagicMock()
    mock_provider.name = "mock"
    mock_provider.supports.return_value = True
    mock_provider.fetch = AsyncMock(return_value=candles)

    with patch.object(registry, "pick", return_value=[mock_provider]):
        result = await registry.fetch("BTCUSDT", "1d", 5)

    assert result is candles
    assert cache.get("BTCUSDT", "1d", 5) is candles


@pytest.mark.asyncio
async def test_registry_fetch_uses_cache_on_second_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OHLCV_CACHE_ENABLED", raising=False)
    candles = _candles(5)

    from tickerflow import registry
    mock_provider = MagicMock()
    mock_provider.name = "mock"
    mock_provider.supports.return_value = True
    mock_provider.fetch = AsyncMock(return_value=candles)

    with patch.object(registry, "pick", return_value=[mock_provider]):
        await registry.fetch("BTCUSDT", "1d", 5)
        await registry.fetch("BTCUSDT", "1d", 5)

    # Provider should only be called once — second call served from cache
    assert mock_provider.fetch.call_count == 1


@pytest.mark.asyncio
async def test_registry_fetch_skips_cache_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OHLCV_CACHE_ENABLED", "false")
    candles = _candles(5)

    from tickerflow import registry
    mock_provider = MagicMock()
    mock_provider.name = "mock"
    mock_provider.supports.return_value = True
    mock_provider.fetch = AsyncMock(return_value=candles)

    with patch.object(registry, "pick", return_value=[mock_provider]):
        await registry.fetch("BTCUSDT", "1d", 5)
        await registry.fetch("BTCUSDT", "1d", 5)

    # Both calls hit the provider when cache is disabled
    assert mock_provider.fetch.call_count == 2
    assert cache.size() == 0
