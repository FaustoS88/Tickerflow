"""Registry fallback with the real providers against the local test server — no network."""

from __future__ import annotations

import asyncio
import time
from collections import Counter

import aiohttp
import pytest

from tests.upstream import Upstream
from tickerflow import registry
from tickerflow.providers import binance
from tickerflow.providers.yfinance import YFinanceProvider

_T0 = 1_763_000_000  # open time of the first fake bar, in seconds

_BINANCE = [
    [(_T0 + i * 86_400) * 1000, "0.030", "0.031", "0.029", "0.0305", "10", 0, "0", 1]
    for i in range(5)
]
_KRAKEN_ROWS = [
    [_T0 + i * 86_400, "0.030", "0.031", "0.029", "0.0306", "0.030", "10", 5] for i in range(5)
]
_KUCOIN_ROWS = [
    [str(_T0 + i * 86_400), "0.030", "0.0307", "0.031", "0.029", "10", "0.3"] for i in range(5)
]
# CoinGecko stamps each 4h bar at its close
_COINGECKO = [[(_T0 + (i + 1) * 14_400) * 1000, 0.0304, 0.0304, 0.0304, 0.0304] for i in range(5)]


def _hits(upstream: Upstream) -> dict[str, int]:
    return dict(Counter(path.split("/")[1] for path, _ in upstream.requests))


@pytest.fixture(autouse=True)
def routed(upstream: Upstream, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OHLCV_CACHE_ENABLED", "false")

    async def no_yahoo(self: YFinanceProvider, symbol: str, interval: str, limit: int) -> None:
        return None

    monkeypatch.setattr(YFinanceProvider, "fetch", no_yahoo)
    upstream.reply("/binance", _BINANCE)
    upstream.reply("/kraken", {"error": [], "result": {"XETHXXBT": _KRAKEN_ROWS, "last": _T0}})
    upstream.reply("/kucoin", {"code": "200000", "data": _KUCOIN_ROWS[::-1]})
    upstream.reply("/coingecko/coins/ethereum/ohlc", _COINGECKO)


def test_binance_serves_two_event_loops_in_a_row(upstream: Upstream) -> None:
    for _ in range(2):
        candles = asyncio.run(registry.fetch("ETHBTC", "1d", 5))
        assert candles[-1].close == 0.0305
    assert _hits(upstream) == {"binance": 2}


@pytest.mark.parametrize("status", [451, 429, 500])
async def test_binance_error_hands_over_to_the_next_exchange(
    upstream: Upstream, status: int
) -> None:
    upstream.reply("/binance", {"error": "fake"}, status=status)
    candles = await registry.fetch("ETHBTC", "1d", 5)
    assert candles[-1].close == 0.0306  # Kraken: same pair, same bar size
    assert _hits(upstream) == {"binance": 1, "kraken": 1}  # CoinGecko has no daily bars


async def test_binance_raising_hands_over_to_the_next_exchange(upstream: Upstream) -> None:
    upstream.reply("/binance", text="<html>not json</html>")
    candles = await registry.fetch("ETHBTC", "1d", 5)
    assert candles[-1].close == 0.0306


async def test_silent_provider_is_skipped_after_the_timeout(
    upstream: Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(binance, "HTTP_TIMEOUT", aiohttp.ClientTimeout(total=0.2))
    upstream.reply("/binance", _BINANCE, delay=2)
    start = time.monotonic()
    candles = await registry.fetch("ETHBTC", "1d", 5)
    assert candles[-1].close == 0.0306
    assert time.monotonic() - start < 1.5


async def test_coingecko_prices_the_pair_in_its_quote_currency(upstream: Upstream) -> None:
    upstream.reply("/binance", status=500)
    candles = await registry.fetch("ETHBTC", "4h", 5)
    queries = [query for path, query in upstream.requests if path.startswith("/coingecko")]
    assert queries == [{"vs_currency": "btc", "days": "30"}]
    assert candles[-1].close == 0.0304
    assert candles[0].time == _T0  # open time, not CoinGecko's close stamp


async def test_daily_ethbtc_is_never_served_by_coingecko(upstream: Upstream) -> None:
    for exchange in ("/binance", "/kraken", "/kucoin"):
        upstream.reply(exchange, status=500)
    assert await registry.fetch("ETHBTC", "1d", 5) is None
    assert "coingecko" not in _hits(upstream)


async def test_all_providers_failing_returns_none(upstream: Upstream) -> None:
    upstream.reset()  # every path answers 404
    assert await registry.fetch("ETHBTC", "4h", 5) is None
