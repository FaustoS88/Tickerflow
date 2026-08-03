"""Example — Pydantic AI agent with tickerflow as a market data tool.

This agent can answer natural language questions about market data by
fetching live OHLCV candles using tickerflow under the hood.

Install:
    pip install tickerflow[ai]

Set your OpenRouter API key:
    export OPENROUTER_API_KEY=sk-or-...

Run:
    python examples/pydantic_ai_agent.py
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from tickerflow import fetch
from tickerflow.registry import teardown

load_dotenv()


class MarketAnalysis(BaseModel):
    """Structured output from the market data agent."""

    symbol: str
    interval: str
    summary: str
    current_price: float | None = None
    price_change_pct: float | None = None
    recommendation: str | None = None


def create_agent(model_or_name: str | OpenAIChatModel | None = None, api_key: str | None = None) -> Agent[None, MarketAnalysis]:
    """Factory function to build the market analysis agent.

    Configures OpenRouter provider if an API key is supplied.
    """
    if model_or_name is None or isinstance(model_or_name, str):
        model_name = model_or_name or "google/gemini-2.5-flash"
        if api_key:
            provider = OpenAIProvider(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )
            model = OpenAIChatModel(model_name, provider=provider)
        else:
            model = model_name
    else:
        model = model_or_name

    agent = Agent(
        model,
        output_type=MarketAnalysis,
        instructions=(
            "You are a market data analyst. When asked about a ticker, "
            "use the fetch_market_data tool to get recent candles, then "
            "provide a concise analysis including current price, recent trend, "
            "and a brief recommendation. Be factual and data-driven."
        ),
    )

    @agent.tool
    async def fetch_market_data(
        ctx: RunContext,
        symbol: str,
        interval: str = "1d",
        limit: int = 30,
    ) -> str:
        """Fetch OHLCV candles for any crypto, stock, or forex ticker.

        Args:
            symbol:   Ticker — e.g. BTCUSDT, AAPL, EURUSD, WM.TO
            interval: Bar size — 1m, 5m, 15m, 1h, 4h, 1d, 1w
            limit:    Number of bars to retrieve (default 30)
        """
        candles = await fetch(symbol.upper(), interval=interval, limit=limit)
        if not candles:
            return f"No data available for {symbol}"

        lines = [f"{'time':>12}  {'open':>10}  {'high':>10}  {'low':>10}  {'close':>10}  {'volume':>14}"]
        for c in candles[-10:]:  # return last 10 to keep context short
            lines.append(
                f"{c.time:>12}  {c.open:>10.4f}  {c.high:>10.4f}  "
                f"{c.low:>10.4f}  {c.close:>10.4f}  {c.volume:>14.2f}"
            )

        return (
            f"{symbol.upper()} — {len(candles)} candles ({interval})\n"
            + "\n".join(lines)
        )

    return agent


async def main() -> None:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY is not set. Running in demonstration mode.")
        print("Set OPENROUTER_API_KEY=sk-or-... to run live queries.")
        return

    agent = create_agent(api_key=api_key)
    questions = [
        "What's the current Bitcoin price and how has it moved this week?",
        "Compare AAPL and MSFT — which stock performed better over the last 10 days?",
    ]

    try:
        for question in questions:
            print(f"\n{'=' * 60}")
            print(f"Q: {question}")
            print("=" * 60)

            result = await agent.run(question)
            analysis = result.output
            print(f"\nSymbol:   {analysis.symbol}")
            print(f"Interval: {analysis.interval}")
            print(f"Summary:  {analysis.summary}")
            if analysis.current_price:
                print(f"Price:    ${analysis.current_price:,.2f}")
            if analysis.price_change_pct is not None:
                print(f"Change:   {analysis.price_change_pct:+.2f}%")
            if analysis.recommendation:
                print(f"Take:     {analysis.recommendation}")
    finally:
        await teardown()


if __name__ == "__main__":
    asyncio.run(main())
