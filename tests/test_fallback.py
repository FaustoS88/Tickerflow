"""Registry fallback with the real providers against a local HTTP server — no network."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator

import aiohttp
import pytest
from aiohttp import web

from tickerflow import registry
from tickerflow.providers import binance, coingecko, kraken, kucoin
from tickerflow.providers.yfinance import YFinanceProvider

_T0 = 1_763_000_000  # open time of the first fake bar, in seconds

# How each fake upstream answers in the current test: "ok", an HTTP status, "garbage" or "hang"
_mode: dict[str, object] = {}
_coingecko_queries: list[dict[str, str]] = []
_hits: dict[str, int] = {}


async def _answer(name: str, payload: object) -> web.Response:
    _hits[name] = _hits.get(name, 0) + 1
    mode = _mode[name]
    if mode == "hang":
        await asyncio.sleep(2)
    if mode == "garbage":
        return web.Response(text="<html>not json</html>")
    if isinstance(mode, int):
        return web.json_response({"error": "fake"}, status=mode)
    return web.json_response(payload)


async def _binance(_: web.Request) -> web.Response:
    rows = [
        [(_T0 + i * 86_400) * 1000, "0.030", "0.031", "0.029", "0.0305", "10", 0, "0", 1]
        for i in range(5)
    ]
    return await _answer("binance", rows)


async def _kraken(_: web.Request) -> web.Response:
    rows = [[_T0 + i * 86_400, "0.030", "0.031", "0.029", "0.0306", "0.030", "10", 5] for i in range(5)]
    return await _answer("kraken", {"error": [], "result": {"XETHXXBT": rows, "last": _T0}})


async def _kucoin(_: web.Request) -> web.Response:
    rows = [[str(_T0 + i * 86_400), "0.030", "0.0307", "0.031", "0.029", "10", "0.3"] for i in range(5)]
    return await _answer("kucoin", {"code": "200000", "data": rows[::-1]})


async def _coingecko(request: web.Request) -> web.Response:
    _coingecko_queries.append(dict(request.query))
    price = 0.0304 if request.query.get("vs_currency") == "btc" else 3050.0
    # CoinGecko stamps each 4h bar at its close
    rows = [[(_T0 + (i + 1) * 14_400) * 1000, price, price, price, price] for i in range(5)]
    return await _answer("coingecko", rows)


@pytest.fixture(scope="module")
def upstream() -> Iterator[str]:
    app = web.Application()
    app.router.add_get("/binance/klines", _binance)
    app.router.add_get("/kraken/OHLC", _kraken)
    app.router.add_get("/kucoin/candles", _kucoin)
    app.router.add_get("/coingecko/coins/{coin}/ohlc", _coingecko)

    # Own loop in a thread, so the server outlives the event loops the tests open and close
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    loop = asyncio.new_event_loop()
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    loop.run_until_complete(web.SockSite(runner, sock).start())
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{sock.getsockname()[1]}"

    asyncio.run_coroutine_threadsafe(runner.cleanup(), loop).result(5)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(5)
    loop.close()


@pytest.fixture(autouse=True)
def routed(upstream: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OHLCV_CACHE_ENABLED", "false")
    monkeypatch.setattr(binance, "_KLINES_URL", f"{upstream}/binance/klines")
    monkeypatch.setattr(kraken, "_BASE_URL", f"{upstream}/kraken/OHLC")
    monkeypatch.setattr(kucoin, "_BASE_URL", f"{upstream}/kucoin/candles")
    monkeypatch.setattr(coingecko, "_BASE_URL", f"{upstream}/coingecko")

    async def no_yahoo(self: YFinanceProvider, symbol: str, interval: str, limit: int) -> None:
        return None

    monkeypatch.setattr(YFinanceProvider, "fetch", no_yahoo)
    _mode.clear()
    _mode.update(binance="ok", coingecko="ok", kraken="ok", kucoin="ok")
    _coingecko_queries.clear()
    _hits.clear()


def test_binance_serves_two_event_loops_in_a_row() -> None:
    for _ in range(2):
        candles = asyncio.run(registry.fetch("ETHBTC", "1d", 5))
        assert candles[-1].close == 0.0305
    assert _hits == {"binance": 2}


@pytest.mark.parametrize("status", [451, 429, 500])
async def test_binance_error_hands_over_to_the_next_exchange(status: int) -> None:
    _mode["binance"] = status
    candles = await registry.fetch("ETHBTC", "1d", 5)
    assert candles[-1].close == 0.0306  # Kraken: same pair, same bar size
    assert _hits == {"binance": 1, "kraken": 1}  # CoinGecko has no daily bars


async def test_binance_raising_hands_over_to_the_next_exchange() -> None:
    _mode["binance"] = "garbage"
    candles = await registry.fetch("ETHBTC", "1d", 5)
    assert candles[-1].close == 0.0306


async def test_silent_provider_is_skipped_after_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(binance, "HTTP_TIMEOUT", aiohttp.ClientTimeout(total=0.2))
    _mode["binance"] = "hang"
    start = time.monotonic()
    candles = await registry.fetch("ETHBTC", "1d", 5)
    assert candles[-1].close == 0.0306
    assert time.monotonic() - start < 1.5


async def test_coingecko_prices_the_pair_in_its_quote_currency() -> None:
    _mode["binance"] = 500
    candles = await registry.fetch("ETHBTC", "4h", 5)
    assert _coingecko_queries == [{"vs_currency": "btc", "days": "30"}]
    assert candles[-1].close == 0.0304
    assert candles[0].time == _T0  # open time, not CoinGecko's close stamp


async def test_daily_ethbtc_is_never_served_by_coingecko() -> None:
    _mode.update(binance=500, kraken=500, kucoin=500)
    assert await registry.fetch("ETHBTC", "1d", 5) is None
    assert _coingecko_queries == []


async def test_all_providers_failing_returns_none() -> None:
    _mode.update(binance=500, coingecko=500, kraken=500, kucoin=500)
    assert await registry.fetch("ETHBTC", "4h", 5) is None
