"""Real requests to the keyless providers, run weekly by the Live workflow — set TICKERFLOW_LIVE=1."""

from __future__ import annotations

import logging
import os
import re
import time

import pytest

from tickerflow import registry
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
_BLOCKED = re.compile(r"(\w+) HTTP (429|451)")


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
async def test_ethbtc_is_priced_in_btc(
    provider: OHLCVProvider, interval: str, caplog: pytest.LogCaptureFixture
) -> None:
    candles = await provider.fetch("ETHBTC", interval, 5)
    if candles is None and (blocked := _BLOCKED.search(caplog.text)):
        pytest.skip(f"{provider.name} answered HTTP {blocked[2]} to this runner")
    close = _last_close(candles, 2 * _DAY)
    assert 0 < close < 1, f"{provider.name} served ETHBTC at {close}, not a BTC price"


async def test_fallback_chain_serves_ethbtc_from_the_first_exchange(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="tickerflow.registry")
    close = _last_close(await registry.fetch("ETHBTC", "1d", 5), 2 * _DAY)
    assert 0 < close < 1, f"the chain served ETHBTC at {close}, not a BTC price"
    # CoinGecko has no 1d bars, so Kraken comes next when Binance turns this runner away
    blocked = _BLOCKED.search(caplog.text)
    expected = "kraken" if blocked and blocked[1] == "binance" else "binance"
    served = re.search(r"provider (\w+) returned \d+ candles", caplog.text)
    assert served and served[1] == expected, caplog.text


async def test_yfinance_serves_aapl() -> None:
    # Five days cover a long weekend before a Monday run
    assert _last_close(await YFinanceProvider().fetch("AAPL", "1d", 5), 5 * _DAY) > 0
