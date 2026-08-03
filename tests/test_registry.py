"""Tests for registry routing — symbol classification → provider chain."""

from __future__ import annotations

import pytest

from tickerflow.registry import pick

# ---------------------------------------------------------------------------
# Crypto
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT", "SOLUSDC", "ETHBTC", "BNBUSDT"])
def test_crypto_routes_to_binance_first(symbol: str) -> None:
    chain = pick(symbol)
    assert chain[0] == "binance"


def test_crypto_includes_yfinance_fallback() -> None:
    names = pick("BTCUSDT")
    assert "yfinance" in names


# ---------------------------------------------------------------------------
# US stocks / indices
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol", ["AAPL", "TSLA", "MSFT", "SPY"])
def test_stock_routes_to_yfinance_first(symbol: str) -> None:
    chain = pick(symbol)
    assert chain[0] == "yfinance"


def test_stock_chain_includes_tiingo_and_finnhub() -> None:
    names = pick("AAPL")
    assert "tiingo" in names
    assert "finnhub" in names


def test_index_symbol_classified_as_stock() -> None:
    chain = pick("^GSPC")
    assert chain[0] == "yfinance"


# ---------------------------------------------------------------------------
# International stocks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol", ["WM.TO", "RIO.L", "OGC.AX"])
def test_intl_stock_routes_to_yfinance_first(symbol: str) -> None:
    chain = pick(symbol)
    assert chain[0] == "yfinance"


def test_intl_stock_chain_includes_finnhub() -> None:
    names = pick("WM.TO")
    assert "finnhub" in names


# ---------------------------------------------------------------------------
# Forex
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("symbol", ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"])
def test_forex_routes_to_yfinance_first(symbol: str) -> None:
    chain = pick(symbol)
    assert chain[0] == "yfinance"


def test_forex_chain_includes_finnhub() -> None:
    names = pick("EURUSD")
    assert "finnhub" in names


# ---------------------------------------------------------------------------
# Chain ordering — market-class providers come before fallbacks
# ---------------------------------------------------------------------------

def test_binance_before_yfinance_for_crypto() -> None:
    names = pick("BTCUSDT")
    assert names.index("binance") < names.index("yfinance")


def test_yfinance_before_tiingo_for_stocks() -> None:
    names = pick("AAPL")
    assert names.index("yfinance") < names.index("tiingo")


def test_yfinance_before_finnhub_for_forex() -> None:
    names = pick("EURUSD")
    assert names.index("yfinance") < names.index("finnhub")
