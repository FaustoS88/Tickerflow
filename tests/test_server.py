"""Tests for the FastAPI server endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tickerflow.models import Candle
from tickerflow.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def sample_candles() -> list[Candle]:
    return [
        Candle(time=1_700_000_000, open=100.0, high=110.0, low=95.0, close=105.0, volume=1000.0),
        Candle(time=1_700_086_400, open=105.0, high=115.0, low=100.0, close=112.0, volume=1500.0),
    ]


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_providers_crypto(client: TestClient) -> None:
    resp = client.get("/providers/BTCUSDT")
    data = resp.json()
    assert data["symbol"] == "BTCUSDT"
    assert "binance" in data["providers"]


def test_providers_stock(client: TestClient) -> None:
    resp = client.get("/providers/AAPL")
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert "yfinance" in data["providers"]


def test_ohlcv_success(client: TestClient, sample_candles: list[Candle]) -> None:
    with patch("tickerflow.server._fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_candles
        resp = client.get("/ohlcv/BTCUSDT?interval=1d&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "BTCUSDT"
        assert data["interval"] == "1d"
        assert data["count"] == 2
        assert len(data["candles"]) == 2
        assert data["candles"][0]["open"] == 100.0


def test_ohlcv_not_found(client: TestClient) -> None:
    with patch("tickerflow.server._fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None
        resp = client.get("/ohlcv/INVALIDSYMBOL?interval=1d&limit=10")
        assert resp.status_code == 404


def test_ohlcv_invalid_interval(client: TestClient) -> None:
    resp = client.get("/ohlcv/BTCUSDT?interval=2h&limit=10")
    assert resp.status_code == 422  # FastAPI validation error


def test_ohlcv_limit_bounds(client: TestClient) -> None:
    resp = client.get("/ohlcv/BTCUSDT?interval=1d&limit=0")
    assert resp.status_code == 422

    resp = client.get("/ohlcv/BTCUSDT?interval=1d&limit=5001")
    assert resp.status_code == 422
