"""Tests for the CLI — tickerflow fetch command."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from tickerflow.cli import main
from tickerflow.models import Candle


def _candles(n: int = 3) -> list[Candle]:
    return [
        Candle(
            time=1_700_000_000 + i * 86_400,
            open=30_000.0 + i,
            high=30_500.0 + i,
            low=29_800.0 + i,
            close=30_200.0 + i,
            volume=100.5 + i,
        )
        for i in range(n)
    ]


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Table output (default)
# ---------------------------------------------------------------------------

def test_fetch_table_output(runner: CliRunner) -> None:
    with patch("tickerflow.cli._registry_fetch", new_callable=AsyncMock, return_value=_candles(3)):
        result = runner.invoke(main, ["fetch", "BTCUSDT", "1d", "3"])
    assert result.exit_code == 0, result.output
    assert "time" in result.output
    assert "open" in result.output
    assert "30000" in result.output


def test_fetch_csv_output(runner: CliRunner) -> None:
    with patch("tickerflow.cli._registry_fetch", new_callable=AsyncMock, return_value=_candles(2)):
        result = runner.invoke(main, ["fetch", "BTCUSDT", "1d", "2", "--csv"])
    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.strip().splitlines() if line]
    assert lines[0] == "time,open,high,low,close,volume"
    assert len(lines) == 3  # header + 2 rows


# ---------------------------------------------------------------------------
# --provider flag
# ---------------------------------------------------------------------------

def test_fetch_with_valid_provider(runner: CliRunner) -> None:
    mock_provider = AsyncMock(return_value=_candles(2))
    mock_provider.name = "binance"
    mock_provider.supports.return_value = True

    with patch("tickerflow.cli.pick", return_value=["binance"]), patch("tickerflow.registry._FACTORIES", {"binance": lambda: mock_provider}):
        result = runner.invoke(main, ["fetch", "BTCUSDT", "1d", "2", "--provider", "binance"])
    assert result.exit_code == 0, result.output


def test_fetch_with_invalid_provider(runner: CliRunner) -> None:
    mock_provider = AsyncMock()
    mock_provider.name = "binance"
    mock_provider.supports.return_value = True

    with patch("tickerflow.cli.pick", return_value=["binance"]):
        result = runner.invoke(main, ["fetch", "BTCUSDT", "1d", "2", "--provider", "nonexistent"])
    assert result.exit_code != 0
    assert "not in chain" in result.output


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_fetch_no_data_exits_nonzero(runner: CliRunner) -> None:
    with patch("tickerflow.cli._registry_fetch", new_callable=AsyncMock, return_value=None):
        result = runner.invoke(main, ["fetch", "BTCUSDT", "1d", "10"])
    assert result.exit_code != 0
    assert "No data" in result.output
