"""Tests for stdlib terminal candlestick chart rendering."""

from __future__ import annotations

from tickerflow.chart import render, render_chart
from tickerflow.models import Candle


def sample_candles() -> list[Candle]:
    return [
        Candle(time=1700000000, open=100.0, high=110.0, low=95.0, close=105.0, volume=1000.0),
        Candle(time=1700086400, open=105.0, high=115.0, low=100.0, close=112.0, volume=1500.0),
        Candle(time=1700172800, open=112.0, high=120.0, low=108.0, close=102.0, volume=2000.0),
    ]


def test_render_chart_returns_nonempty_string() -> None:
    candles = sample_candles()
    output = render(candles, symbol="BTCUSDT", interval="1d", color=False)
    assert "BTCUSDT" in output
    assert "1d" in output
    assert "vol" in output


def test_render_chart_empty_candles() -> None:
    output = render([], symbol="BTCUSDT", interval="1d")
    assert "No candles to chart" in output


def test_render_chart_helper(capsys) -> None:
    candles = sample_candles()
    render_chart(candles, symbol="AAPL", interval="1d")
    captured = capsys.readouterr()
    assert "AAPL" in captured.out
