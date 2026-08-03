"""Tests for the pandas DataFrame output feature."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from tickerflow.models import Candle
from tickerflow.registry import _candles_to_dataframe


@pytest.fixture
def sample_candles() -> list[Candle]:
    return [
        Candle(time=1_700_000_000, open=100.0, high=110.0, low=95.0, close=105.0, volume=1000.0),
        Candle(time=1_700_086_400, open=105.0, high=115.0, low=100.0, close=112.0, volume=1500.0),
        Candle(time=1_700_172_800, open=112.0, high=120.0, low=108.0, close=118.0, volume=2000.0),
    ]


def test_dataframe_columns(sample_candles: list[Candle]) -> None:
    df = _candles_to_dataframe(sample_candles)
    assert list(df.columns) == ["time", "open", "high", "low", "close", "volume"]


def test_dataframe_row_count(sample_candles: list[Candle]) -> None:
    df = _candles_to_dataframe(sample_candles)
    assert len(df) == 3


def test_dataframe_time_is_datetime(sample_candles: list[Candle]) -> None:
    import pandas as pd

    df = _candles_to_dataframe(sample_candles)
    assert pd.api.types.is_datetime64_any_dtype(df["time"])


def test_dataframe_time_is_utc(sample_candles: list[Candle]) -> None:
    df = _candles_to_dataframe(sample_candles)
    assert str(df["time"].dt.tz) == "UTC"


def test_dataframe_values_match(sample_candles: list[Candle]) -> None:
    df = _candles_to_dataframe(sample_candles)
    assert df["open"].tolist() == [100.0, 105.0, 112.0]
    assert df["close"].tolist() == [105.0, 112.0, 118.0]
    assert df["volume"].tolist() == [1000.0, 1500.0, 2000.0]


def test_dataframe_missing_pandas(sample_candles: list[Candle]) -> None:
    """Verify a clear ImportError is raised when pandas is not installed."""
    with (
        patch.dict(sys.modules, {"pandas": None}),
        pytest.raises(ImportError, match=r'pip install "tickerflow\[pandas\]"'),
    ):
        _candles_to_dataframe(sample_candles)


def test_dataframe_empty_list() -> None:
    df = _candles_to_dataframe([])
    assert len(df) == 0
    assert list(df.columns) == ["time", "open", "high", "low", "close", "volume"]
