"""Minimal example — fetch the last 10 daily candles for a few symbols.

Run:
    python examples/basic_fetch.py
"""

from __future__ import annotations

import asyncio

from tickerflow import fetch


async def main() -> None:
    symbols = [
        ("BTCUSDT", "1d", 10),   # crypto  → Binance
        ("AAPL",    "1d", 10),   # US stock → yfinance
        ("EURUSD",  "1d", 10),   # forex    → yfinance
    ]

    for symbol, interval, limit in symbols:
        print(f"\n{symbol} ({interval}, last {limit} bars)")
        candles = await fetch(symbol, interval=interval, limit=limit)

        if not candles:
            print("  no data returned")
            continue

        print(f"  {'time':>10}  {'open':>10}  {'high':>10}  {'low':>10}  {'close':>10}")
        for c in candles[-5:]:
            print(f"  {c.time:>10}  {c.open:>10.4f}  {c.high:>10.4f}  {c.low:>10.4f}  {c.close:>10.4f}")


asyncio.run(main())
