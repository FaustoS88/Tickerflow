"""Shared fixtures: the exchange providers talk to a local server instead of the network."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.upstream import Upstream
from tickerflow.providers import binance, coingecko, kraken, kucoin


@pytest.fixture(scope="session")
def _server() -> Iterator[Upstream]:
    server = Upstream()
    server.start()
    yield server
    server.stop()


@pytest.fixture()
def upstream(_server: Upstream, monkeypatch: pytest.MonkeyPatch) -> Upstream:
    """The local server with no replies set, and the exchange URLs pointed at it."""
    _server.reset()
    monkeypatch.setattr(binance, "_KLINES_URL", f"{_server.url}/binance/klines")
    monkeypatch.setattr(kraken, "_BASE_URL", f"{_server.url}/kraken/OHLC")
    monkeypatch.setattr(kucoin, "_BASE_URL", f"{_server.url}/kucoin/candles")
    monkeypatch.setattr(coingecko, "_BASE_URL", f"{_server.url}/coingecko")
    return _server
