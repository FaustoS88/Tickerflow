"""Tests for the Pydantic AI agent integration example."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.models.test import TestModel

from examples.pydantic_ai_agent import MarketAnalysis, create_agent
from tickerflow.models import Candle


@pytest.fixture
def sample_candles() -> list[Candle]:
    return [
        Candle(time=1_700_000_000, open=100.0, high=110.0, low=95.0, close=105.0, volume=1000.0),
        Candle(time=1_700_086_400, open=105.0, high=115.0, low=100.0, close=112.0, volume=1500.0),
    ]


@pytest.mark.asyncio
async def test_pydantic_ai_agent_with_test_model(sample_candles: list[Candle]) -> None:
    expected_data = {
        "symbol": "BTCUSDT",
        "interval": "1d",
        "summary": "Bitcoin shows bullish momentum",
        "current_price": 112.0,
        "price_change_pct": 6.67,
        "recommendation": "Hold",
    }
    test_model = TestModel(
        call_tools="all",
        custom_output_args=expected_data,
    )

    agent = create_agent(model_or_name=test_model)

    with patch("tickerflow.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_candles

        result = await agent.run("Analyze BTCUSDT daily chart")

        assert isinstance(result.output, MarketAnalysis)
        assert result.output.symbol == "BTCUSDT"
        assert result.output.current_price == 112.0
        assert result.output.recommendation == "Hold"


@pytest.mark.asyncio
async def test_agent_tool_fetch_market_data_empty() -> None:
    expected_data = {
        "symbol": "INVALID",
        "interval": "1d",
        "summary": "No data found",
    }
    test_model = TestModel(
        call_tools="all",
        custom_output_args=expected_data,
    )

    agent = create_agent(model_or_name=test_model)

    with patch("tickerflow.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None

        result = await agent.run("Analyze INVALID ticker")
        assert result.output.symbol == "INVALID"
