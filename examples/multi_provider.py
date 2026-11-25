"""Example — inspect provider chains and observe fallback behaviour.

Shows which providers are in the chain for each asset class, then fetches
live data and reports which provider actually served the response.

Run:
    python examples/multi_provider.py
"""

from __future__ import annotations

import asyncio
import logging

from tickerflow import NoDataError, fetch
from tickerflow.registry import pick

logging.basicConfig(level=logging.WARNING)  # suppress provider debug noise


async def main() -> None:
    symbols = [
        ("BTCUSDT", "1d", 5),   # crypto  — Binance primary
        ("AAPL",    "1d", 5),   # US stock — yfinance primary
        ("RY.TO",   "1d", 5),   # intl stock — yfinance primary
        ("EURUSD",  "1d", 5),   # forex   — yfinance primary
    ]

    for symbol, interval, limit in symbols:
        chain = pick(symbol)
        chain_str = " → ".join(chain)
        print(f"\n{symbol}  [{interval}]")
        print(f"  chain : {chain_str}")

        try:
            candles = await fetch(symbol, interval=interval, limit=limit)
        except NoDataError as e:
            print(f"  result: {e}")
            continue
        last = candles[-1]
        print(f"  served: {candles.provider}")
        print(f"  bars  : {len(candles)}")
        print(f"  last  : O={last.open:.4f}  H={last.high:.4f}  L={last.low:.4f}  C={last.close:.4f}")


asyncio.run(main())
