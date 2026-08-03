"""Example — fetch OHLCV data as a pandas DataFrame for quick analysis.

Install pandas first:
    pip install "tickerflow[pandas]"

Run:
    python examples/pandas_output.py
"""

from __future__ import annotations

import asyncio

from tickerflow import fetch


async def main() -> None:
    # Fetch 30 daily candles for BTC as a DataFrame
    df = await fetch("BTCUSDT", interval="1d", limit=30, as_dataframe=True)

    if df is None or df.empty:
        print("No data returned")
        return

    print("=== BTCUSDT — Last 30 Daily Candles ===\n")
    print(df.to_string(index=False))

    print("\n=== Summary Statistics ===\n")
    print(df[["open", "high", "low", "close", "volume"]].describe().to_string())

    print(f"\n  Highest close: {df['close'].max():.2f}")
    print(f"  Lowest close:  {df['close'].min():.2f}")
    print(f"  Avg volume:    {df['volume'].mean():,.0f}")


asyncio.run(main())
