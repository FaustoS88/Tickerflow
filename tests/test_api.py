"""The 0.3.0 API against the real providers and the local test server: reasons, ranges, deadline."""

from __future__ import annotations

import asyncio
import datetime
import pickle
import time
from collections.abc import Callable

import pandas as pd
import pytest

from tests.upstream import Upstream
from tickerflow import NoDataError, fetch, fetch_df
from tickerflow.providers.kraken import KrakenProvider
from tickerflow.providers.yfinance import YFinanceProvider

_DAY = 86_400
_T0 = 1_600_000_000 // _DAY * _DAY  # open time of the first fake bar
_N = 2_500  # bars the fake exchanges hold
_OPENS = [_T0 + i * _DAY for i in range(_N)]


def _binance(query: dict[str, str]) -> list[list[object]]:
    """Like Binance: the newest `limit` bars that open at or before endTime."""
    end = int(query.get("endTime", 10**15)) // 1000
    opens = [t for t in _OPENS if t <= end][-int(query["limit"]) :]
    return [[t * 1000, "0.03", "0.031", "0.029", "0.0305", "10", 0, "0", 1] for t in opens]


def _kucoin(query: dict[str, str]) -> dict[str, object]:
    """Like KuCoin: the newest 1,500 bars inside [startAt, endAt], newest first."""
    start, end = int(query["startAt"]), int(query["endAt"])
    opens = [t for t in _OPENS if start <= t <= end][-1500:]
    rows = [[str(t), "0.03", "0.0307", "0.031", "0.029", "10", "0.3"] for t in opens]
    return {"code": "200000", "data": rows[::-1]}


def _kraken_rows(last: int) -> dict[str, object]:
    rows = [[t, "0.03", "0.031", "0.029", "0.0306", "0.03", "10", 5] for t in _OPENS[last - 720 : last]]
    return {"error": [], "result": {"XETHXXBT": rows, "last": _OPENS[last - 1]}}


def _hits(upstream: Upstream, exchange: str) -> int:
    return sum(path.startswith(f"/{exchange}") for path, _ in upstream.requests)


@pytest.fixture(autouse=True)
def routed(upstream: Upstream, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OHLCV_CACHE_ENABLED", "false")

    async def no_yahoo(self: YFinanceProvider, *args: object) -> None:
        return None

    monkeypatch.setattr(YFinanceProvider, "fetch", no_yahoo)
    monkeypatch.setattr(YFinanceProvider, "fetch_range", no_yahoo)
    upstream.reply("/binance", _binance)
    upstream.reply("/kucoin", _kucoin)
    upstream.reply("/kraken", _kraken_rows(_N))


async def test_binance_pages_back_past_1000_bars(upstream: Upstream) -> None:
    candles = await fetch("ETHBTC", "1d", 2_200)
    assert [c.time for c in candles] == _OPENS[-2_200:]
    assert candles.provider == "binance"
    assert _hits(upstream, "binance") == 3


async def test_binance_serves_a_date_range_in_pages(upstream: Upstream) -> None:
    start = datetime.datetime.fromtimestamp(_OPENS[100], datetime.UTC)
    candles = await fetch("ETHBTC", "1d", start=start, end=_OPENS[2_300])
    assert [c.time for c in candles] == _OPENS[100:2_300]
    assert _hits(upstream, "binance") == 3


async def test_kucoin_serves_a_date_range_in_pages(upstream: Upstream) -> None:
    candles = await fetch("ETHBTC", "1d", start=_OPENS[200], end=_OPENS[2_400], providers=["kucoin"])
    assert [c.time for c in candles] == _OPENS[200:2_400]
    assert candles.provider == "kucoin"
    assert _hits(upstream, "kucoin") == 2


async def test_kraken_explains_history_beyond_its_last_720_bars() -> None:
    with pytest.raises(NoDataError) as err:
        await fetch("ETHBTC", "1d", start=_OPENS[0], providers=["kraken"])
    oldest = datetime.datetime.fromtimestamp(_OPENS[_N - 720], datetime.UTC)
    assert err.value.reasons == {
        "kraken": f"serves only its last 720 1d bars, from {oldest:%Y-%m-%d %H:%M} UTC"
    }


async def test_kraken_serves_the_whole_history_of_a_young_pair(upstream: Upstream) -> None:
    rows = [[t, "0.03", "0.031", "0.029", "0.0306", "0.03", "10", 5] for t in _OPENS[-30:]]
    upstream.reply("/kraken", {"error": [], "result": {"XETHXXBT": rows, "last": _OPENS[-1]}})
    candles = await KrakenProvider().fetch_range("ETHBTC", "1d", _OPENS[0], _OPENS[-1] + _DAY)
    assert [c.time for c in candles] == _OPENS[-30:]


async def test_kraken_serves_a_range_inside_its_last_720_bars() -> None:
    candles = await KrakenProvider().fetch_range("ETHBTC", "1d", _OPENS[_N - 100], _OPENS[_N - 10])
    assert [c.time for c in candles] == _OPENS[_N - 100 : _N - 10]


async def test_the_result_names_the_provider_that_served_it(upstream: Upstream) -> None:
    upstream.reply("/binance", status=451)
    candles = await fetch("ETHBTC", "1d", 5)
    df = await fetch_df("ETHBTC", "1d", 5)
    assert candles.provider == "kraken"
    assert df.attrs["provider"] == "kraken"
    assert len(df) == 5 and isinstance(df, pd.DataFrame)


async def test_a_range_skips_providers_without_history(upstream: Upstream) -> None:
    upstream.reply("/binance", status=451)
    candles = await fetch("ETHBTC", "4h", start=_OPENS[0], end=_OPENS[3])
    assert candles.provider == "kucoin"  # CoinGecko serves no ranges, Kraken has no history


async def test_the_deadline_covers_the_whole_chain(upstream: Upstream) -> None:
    upstream.reply("/binance", _binance, delay=3)
    began = time.monotonic()
    with pytest.raises(NoDataError) as err:
        await fetch("ETHBTC", "1d", 5, timeout=0.3)
    assert time.monotonic() - began < 1
    assert err.value.reasons == {"binance": "stopped at the 0.3 s deadline"}


async def test_the_deadline_covers_yfinance(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow(self: YFinanceProvider, *args: object) -> None:
        await asyncio.to_thread(time.sleep, 1)

    monkeypatch.setattr(YFinanceProvider, "fetch", slow)
    began = time.monotonic()
    with pytest.raises(NoDataError, match="yfinance: stopped at the 0.2 s deadline"):
        await fetch("AAPL", "1d", 5, timeout=0.2)
    assert time.monotonic() - began < 0.8


def test_no_data_error_survives_pickle() -> None:
    error = pickle.loads(pickle.dumps(NoDataError("ETHBTC", "1d", {"kraken": "HTTP 500"})))
    assert error.reasons == {"kraken": "HTTP 500"}
    assert str(error) == "no data for ETHBTC 1d: kraken: HTTP 500"


async def test_no_supporting_provider_is_said_plainly() -> None:
    with pytest.raises(NoDataError, match="^no data for BTCUSDT 1D 5 1d: no provider supports BTCUSDT 1D 5$"):
        await fetch("BTCUSDT 1D 5", "1d")


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: fetch("ETHBTC", "1D"), "interval '1D' is not one of 1m, 3m"),
        (lambda: fetch("ETHBTC", "1d", 0), "limit must be at least 1, got 0"),
        (lambda: fetch("ETHBTC", "1d", 5, start=_T0), "pass limit or start, not both"),
        (lambda: fetch("ETHBTC", "1d", end=_T0), "end needs start"),
        (lambda: fetch("ETHBTC", "1d", start=_T0, end=_T0), "start must be before end"),
        (lambda: fetch("ETHBTC", start=datetime.datetime(2025, 1, 1)), "start must be timezone-aware"),
        (lambda: fetch("ETHBTC", providers=["bitstamp"]), "unknown provider 'bitstamp'"),
        (lambda: fetch("ETHBTC", providers="binance"), "providers takes a non-empty list"),
        (lambda: fetch("ETHBTC", providers=[]), "providers takes a non-empty list"),
    ],
)
async def test_invalid_arguments_raise_before_any_request(
    upstream: Upstream, call: Callable[[], object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        await call()  # type: ignore[misc]
    assert upstream.requests == []
