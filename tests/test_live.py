"""Real requests to the keyless providers, run weekly by the Live workflow — set TICKERFLOW_LIVE=1."""

from __future__ import annotations

import logging
import os
import re
import time

import pytest

from tickerflow import ProviderError, fetch
from tickerflow.models import Candle
from tickerflow.providers.base import OHLCVProvider
from tickerflow.providers.binance import BinanceProvider
from tickerflow.providers.coingecko import CoinGeckoProvider
from tickerflow.providers.kraken import KrakenProvider
from tickerflow.providers.kucoin import KuCoinProvider
from tickerflow.providers.yfinance import YFinanceProvider

pytestmark = pytest.mark.skipif(
    os.environ.get("TICKERFLOW_LIVE") != "1", reason="live network test, set TICKERFLOW_LIVE=1"
)

_DAY = 86_400
# Region blocks and rate limits on shared runner IPs say nothing about tickerflow
_BLOCKED = re.compile(r"HTTP (429|451)")


async def _or_skip_if_blocked(provider: OHLCVProvider, call: object) -> list[Candle] | None:
    try:
        return await call  # type: ignore[misc]
    except ProviderError as e:
        if blocked := _BLOCKED.fullmatch(str(e)):
            pytest.skip(f"{provider.name} answered HTTP {blocked[1]} to this runner")
        raise


def _last_close(candles: list[Candle] | None, max_age: int) -> float:
    assert candles, "no bars"
    assert len(candles) == 5
    times = [c.time for c in candles]
    assert times == sorted(times)
    assert time.time() - times[-1] < max_age, "last bar is stale"
    return candles[-1].close


@pytest.mark.parametrize(
    ("provider", "interval"),
    [
        (BinanceProvider(), "1d"),
        (KrakenProvider(), "1d"),
        (KuCoinProvider(), "1d"),
        (CoinGeckoProvider(), "4h"),
    ],
    ids=lambda p: getattr(p, "name", p),
)
async def test_ethbtc_is_priced_in_btc(provider: OHLCVProvider, interval: str) -> None:
    candles = await _or_skip_if_blocked(provider, provider.fetch("ETHBTC", interval, 5))
    close = _last_close(candles, 2 * _DAY)
    assert 0 < close < 1, f"{provider.name} served ETHBTC at {close}, not a BTC price"


async def test_fallback_chain_serves_ethbtc_from_the_first_exchange(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="tickerflow.registry")
    candles = await fetch("ETHBTC", "1d", 5)
    close = _last_close(candles, 2 * _DAY)
    assert 0 < close < 1, f"the chain served ETHBTC at {close}, not a BTC price"
    # CoinGecko has no 1d bars, so Kraken comes next when Binance turns this runner away
    blocked = re.search(r"provider binance failed for ETHBTC 1d: HTTP (429|451)", caplog.text)
    assert candles.provider == ("kraken" if blocked else "binance"), caplog.text


@pytest.mark.parametrize("provider", [BinanceProvider(), KuCoinProvider()], ids=lambda p: p.name)
async def test_a_date_range_is_paged_back(provider: OHLCVProvider) -> None:
    # 2,000 hourly bars: two pages or more on both exchanges
    end = int(time.time()) // 3_600 * 3_600 - 3 * _DAY
    start = end - 2_000 * 3_600
    candles = await _or_skip_if_blocked(
        provider, provider.fetch_range("ETHBTC", "1h", start, end)
    )
    assert candles, "no bars"
    times = [c.time for c in candles]
    assert times == sorted(set(times)), "bars out of order or repeated"
    assert start <= times[0] and times[-1] < end
    assert len(times) > 1_900, f"{len(times)} bars for 2,000 hours"


async def test_yfinance_serves_aapl() -> None:
    # Five days cover a long weekend before a Monday run
    assert _last_close(await YFinanceProvider().fetch("AAPL", "1d", 5), 5 * _DAY) > 0
