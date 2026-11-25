# tickerflow

**Async OHLCV for crypto, stocks and forex behind one `fetch()` call.**
Crypto needs no API keys and falls back across Binance, CoinGecko (4h only), Kraken, KuCoin and Yahoo Finance.
Stocks and forex come from yfinance; Tiingo (stocks) and Finnhub are fallbacks once you add a key.

[![CI](https://github.com/FaustoS88/Tickerflow/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/FaustoS88/Tickerflow/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tickerflow?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/tickerflow/)
[![Python](https://img.shields.io/pypi/pyversions/tickerflow?logo=python&logoColor=white&style=flat-square)](https://pypi.org/project/tickerflow/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](https://github.com/FaustoS88/Tickerflow/blob/main/LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/FaustoS88/Tickerflow?style=social)](https://github.com/FaustoS88/Tickerflow)

---

```python
import asyncio
from tickerflow import fetch

async def main():
    btc = await fetch("BTCUSDT")    # crypto  → Binance → CoinGecko → Kraken → KuCoin → yfinance
    aapl = await fetch("AAPL")      # stocks  → yfinance → Tiingo → Finnhub
    eur = await fetch("EURUSD")     # forex   → yfinance → Finnhub
    print(btc[-1].close, aapl[-1].close, eur[-1].close)

asyncio.run(main())
```

Real output of the CLI, run on 2026-11-25 (times are Unix seconds, bar open):

```console
$ tickerflow fetch BTCUSDT 1d 5

        time        open        high         low       close          volume
  1795219200  58951.5100  60996.0000  55130.0000  60215.7700        48558.10
  1795305600  60215.7800  61669.9900  58768.5100  61271.0800        20137.13
  1795392000  61271.0900  64603.1200  60386.0000  61270.9300        27493.88
  1795478400  61270.9200  61682.0100  59260.0000  59832.0000        19707.40
  1795564800  59832.0000  59950.0000  57300.3800  59674.4400        21870.02

$ tickerflow chart BTCUSDT 1d 30 --no-color
BTCUSDT · 1d · 30 candles
 83,313
        ███     ││
        █│█     ██
          ████████
 76,366    ││ ██│████│
                 ││ █████
                    ││││█
                        ██
                         █
 67,682                  ██
                          ███│
                          █████│   │
                          ││ │███ │││
 60,735                        │█████│
                                ██│ ██
                                ││   │
                                 │
 53,788
        ┼──────────────────────────────
    vol                          █
                          █     ██
          ██    ██       █████████████
        ███████████ ██████████████████
        27/10       10/11        25/11
```

## Limitations

- Without API keys, stocks and forex have a single source (yfinance).
- `4h` bars are available for crypto only.
- Crypto pairs quoted in fiat, such as `BTCEUR`, are read as forex and return no data.
- `fetch()` returns the most recent bars only (up to 1,000 on Binance, 1,500 on KuCoin, 720 on Kraken); there is no date-range query yet.
- On exchanges the last bar is the current, unfinished one, and cached results are reused for the interval's TTL (4 hours for `1d`).
- CoinGecko serves `4h` bars only (up to 180), without volume, and prices stablecoin pairs in USD.

## Install

```bash
pip install tickerflow
```

Extras for power users:

```bash
pip install "tickerflow[pandas]"   # DataFrame output
pip install "tickerflow[serve]"    # self-hosted API server
pip install "tickerflow[ai]"       # Pydantic AI integration
pip install "tickerflow[all]"      # everything
```

## Quick Start

```python
import asyncio
from tickerflow import fetch

async def main():
    # Fetch 10 daily candles — provider is auto-selected
    candles = await fetch("BTCUSDT", interval="1d", limit=10)
    for c in candles[-3:]:
        print(f"{c.time}  O:{c.open:.2f}  H:{c.high:.2f}  L:{c.low:.2f}  C:{c.close:.2f}")

    # Want a DataFrame instead? One flag.
    df = await fetch("AAPL", interval="1d", limit=30, as_dataframe=True)
    print(df.describe())

asyncio.run(main())
```

## CLI

```bash
# Auto-routes to the best provider
tickerflow fetch BTCUSDT 1d 10

# Force a provider
tickerflow fetch EURUSD 1d 20 --provider yfinance

# Output formats
tickerflow fetch AAPL 1d 10 --csv
tickerflow fetch AAPL 1d 10 --json

# Terminal chart — screenshot-worthy
tickerflow chart BTCUSDT 1d 30

# Self-hosted market data API
tickerflow serve --port 8000
```

## Terminal Chart

Render OHLCV data directly in your terminal with `tickerflow chart`:

```bash
tickerflow chart BTCUSDT 1d 30
```

Renders Unicode candlestick charts with ANSI green/red coloring and a volume pane — pure stdlib, zero dependencies. Supports `--no-color` and respects `NO_COLOR`.

No extra install needed — included in the base package.

## Self-Hosted API

One command starts a FastAPI server with live market data endpoints:

```bash
tickerflow serve --port 8000
```

Then:

```bash
curl localhost:8000/ohlcv/BTCUSDT?interval=1d&limit=5
curl localhost:8000/providers/BTCUSDT
curl localhost:8000/health
```

Returns structured JSON — plug it into any frontend, dashboard, or automation. No vendor lock-in, runs on your machine; the upstream providers keep their own rate limits.

By default the server binds to `0.0.0.0` and allows any CORS origin; pass `--host 127.0.0.1` to keep it local.

Requires: `pip install "tickerflow[serve]"`

## DataFrame Output

Prefer a DataFrame? One flag:

```python
df = await fetch("BTCUSDT", interval="1d", limit=30, as_dataframe=True)
print(df.describe())
```

Returns a `pandas.DataFrame` with columns `time` (UTC datetime), `open`, `high`, `low`, `close`, `volume`.

Requires: `pip install "tickerflow[pandas]"`

## Provider Routing

The router automatically detects asset class from the symbol and tries providers in order. If one fails, the next picks up.

```
BTCUSDT  →  Binance  →  CoinGecko  →  Kraken  →  KuCoin  →  yfinance
AAPL     →  yfinance  →  Tiingo (daily/weekly)  →  Finnhub
RY.TO    →  yfinance  →  Finnhub
EURUSD   →  yfinance  →  Finnhub
```

| Provider  | Key required | Asset classes         |
|-----------|--------------|-----------------------|
| Binance   | No           | Crypto                |
| KuCoin    | No           | Crypto                |
| Kraken    | No           | Crypto                |
| CoinGecko | No           | Crypto (`4h` only)    |
| yfinance  | No           | Stocks, Forex, Crypto |
| Tiingo    | Yes (free)   | Stocks, ETFs          |
| Finnhub   | Yes (paid)   | Stocks, Forex         |

## Supported Intervals

`1m` · `5m` · `15m` · `1h` · `4h` · `1d` · `1w`

## Caching

Responses are cached in memory with interval-aware TTLs:

| Interval | TTL   |
|----------|-------|
| `1m`     | 30s   |
| `5m`     | 2 min |
| `15m`    | 5 min |
| `1h`     | 30 min |
| `4h`     | 2h    |
| `1d`     | 4h    |
| `1w`     | 24h   |

Disable: `OHLCV_CACHE_ENABLED=false`

## Pydantic AI Integration

Use tickerflow as a tool in your [Pydantic AI](https://github.com/pydantic/pydantic-ai) agents:

```python
from pydantic_ai import Agent
from tickerflow import fetch

agent = Agent("openai:gpt-4o", instructions="You are a market analyst.")

@agent.tool
async def fetch_market_data(ctx, symbol: str, interval: str = "1d", limit: int = 30) -> str:
    candles = await fetch(symbol, interval=interval, limit=limit)
    if not candles:
        return f"No data for {symbol}"
    last = candles[-1]
    return f"{symbol}: O={last.open:.2f} H={last.high:.2f} L={last.low:.2f} C={last.close:.2f}"
```

See [examples/pydantic_ai_agent.py](https://github.com/FaustoS88/Tickerflow/blob/main/examples/pydantic_ai_agent.py) for a complete working agent.

Requires: `pip install "tickerflow[ai]"`

## Why This Exists

I built tickerflow because I was tired of wiring up different API clients for crypto vs stocks vs forex. I wanted one async `fetch()` call that handles everything — and falls back automatically when a provider is down.

It is meant for scripts, AI agents and small trading tools that need multi-asset OHLCV data without setting up one client per provider.

## Examples

See [examples/](https://github.com/FaustoS88/Tickerflow/tree/main/examples) for runnable scripts:

- [basic_fetch.py](https://github.com/FaustoS88/Tickerflow/blob/main/examples/basic_fetch.py) — fetch candles for crypto, stock, and forex
- [multi_provider.py](https://github.com/FaustoS88/Tickerflow/blob/main/examples/multi_provider.py) — inspect provider chains and observe fallback
- [pandas_output.py](https://github.com/FaustoS88/Tickerflow/blob/main/examples/pandas_output.py) — DataFrame output for quick analysis
- [pydantic_ai_agent.py](https://github.com/FaustoS88/Tickerflow/blob/main/examples/pydantic_ai_agent.py) — AI agent with market data tools

## Roadmap

**Shipped in v0.2**
- pandas DataFrame output
- `tickerflow serve` — self-hosted FastAPI market data API
- `tickerflow chart` — terminal candlestick charts
- Pydantic AI integration example

**Planned**
- OKX and Bybit providers
- WebSocket streaming
- Date-range queries with pagination where the exchange allows it
- Async context manager support

## Contributing

See [CONTRIBUTING.md](https://github.com/FaustoS88/Tickerflow/blob/main/CONTRIBUTING.md) for development setup, how to add providers, and PR guidelines.

## License

MIT
