"""Command-line interface for tickerflow.

Usage examples:
    tickerflow fetch BTCUSDT
    tickerflow fetch AAPL 1d 30
    tickerflow fetch EURUSD 1h 50 --provider yfinance
    tickerflow fetch BTCUSDT 1d 10 --csv
    tickerflow fetch BTCUSDT 1d 10 --json
    tickerflow serve --port 8000
    tickerflow chart BTCUSDT 1d 30
"""

from __future__ import annotations

import asyncio
import json

import click
from dotenv import load_dotenv

from tickerflow.errors import NoDataError
from tickerflow.models import Candles
from tickerflow.registry import fetch as _registry_fetch
from tickerflow.registry import pick

load_dotenv()  # load .env from cwd or any parent directory


@click.group()
def main() -> None:
    """tickerflow — fetch OHLCV market data from the command line."""


@main.command()
@click.argument("symbol")
@click.argument("interval", default="1d")
@click.argument("limit", default=100, type=int)
@click.option(
    "--provider",
    "provider_name",
    default=None,
    help="Force a specific provider (binance, yfinance, tiingo, finnhub).",
)
@click.option(
    "--csv",
    "output_csv",
    is_flag=True,
    default=False,
    help="Output rows as CSV instead of a formatted table.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Output rows as JSON array.",
)
def fetch(
    symbol: str,
    interval: str,
    limit: int,
    provider_name: str | None,
    output_csv: bool,
    output_json: bool,
) -> None:
    """Fetch OHLCV candles for SYMBOL.

    SYMBOL   Ticker symbol — e.g. BTCUSDT, AAPL, EURUSD, RY.TO\n
    INTERVAL Bar size      — 1m 5m 15m 1h 4h 1d 1w  (default: 1d)\n
    LIMIT    Number of bars to return              (default: 100)
    """
    asyncio.run(_run_fetch(symbol.upper(), interval, limit, provider_name, output_csv, output_json))


async def _run_fetch(
    symbol: str,
    interval: str,
    limit: int,
    provider_name: str | None,
    output_csv: bool,
    output_json: bool,
) -> None:
    if provider_name and provider_name.lower() not in (available := pick(symbol)):
        raise click.ClickException(
            f"Provider '{provider_name}' not in chain for {symbol}. "
            f"Available: {', '.join(available)}"
        )
    candles = await _fetch_or_fail(
        symbol, interval, limit, [provider_name.lower()] if provider_name else None
    )

    if output_json:
        rows = [
            {
                "time": c.time,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
        click.echo(json.dumps(rows, indent=2))
    elif output_csv:
        click.echo("time,open,high,low,close,volume")
        for c in candles:
            click.echo(f"{c.time},{c.open},{c.high},{c.low},{c.close},{c.volume}")
    else:
        click.echo(
            f"\n{'time':>12}  {'open':>10}  {'high':>10}  "
            f"{'low':>10}  {'close':>10}  {'volume':>14}"
        )
        for c in candles:
            click.echo(
                f"{c.time:>12}  {c.open:>10.4f}  {c.high:>10.4f}  "
                f"{c.low:>10.4f}  {c.close:>10.4f}  {c.volume:>14.2f}"
            )


async def _fetch_or_fail(
    symbol: str, interval: str, limit: int, providers: list[str] | None = None
) -> Candles:
    try:
        return await _registry_fetch(symbol, interval, limit, providers=providers)
    except (NoDataError, ValueError) as e:
        raise click.ClickException(str(e)) from None


@main.command()
@click.argument("symbol")
@click.argument("interval", default="1d")
@click.argument("limit", default=30, type=int)
@click.option("--no-color", is_flag=True, default=False, help="Disable ANSI colors.")
def chart(symbol: str, interval: str, limit: int, no_color: bool) -> None:
    """Render a terminal chart for SYMBOL.

    SYMBOL   Ticker symbol — e.g. BTCUSDT, AAPL, EURUSD\n
    INTERVAL Bar size      — 1m 5m 15m 1h 4h 1d 1w  (default: 1d)\n
    LIMIT    Number of bars to chart               (default: 30)
    """
    asyncio.run(_run_chart(symbol.upper(), interval, limit, no_color=no_color))


async def _run_chart(symbol: str, interval: str, limit: int, no_color: bool = False) -> None:
    candles = await _fetch_or_fail(symbol, interval, limit)

    from tickerflow import chart

    click.echo(chart.render(candles, symbol, interval, color=not no_color if no_color else None))


@main.command()
@click.option("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0).")
@click.option("--port", default=8000, type=int, help="Bind port (default: 8000).")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload for development.")
def serve(host: str, port: int, reload: bool) -> None:
    """Start a self-hosted market data API server.

    Runs a FastAPI server with endpoints:

    \b
      GET /ohlcv/{symbol}?interval=1d&limit=100
      GET /providers/{symbol}
      GET /health
    """
    try:
        import uvicorn
    except ImportError:
        raise click.ClickException(
            "uvicorn is required for the server. "
            "Install with: pip install \"tickerflow[serve]\""
        )

    click.echo(f"Starting tickerflow API server on {host}:{port}")
    click.echo(f"  GET http://{host}:{port}/ohlcv/BTCUSDT?interval=1d&limit=10")
    click.echo(f"  GET http://{host}:{port}/providers/BTCUSDT")
    click.echo(f"  GET http://{host}:{port}/health")
    click.echo()

    uvicorn.run(
        "tickerflow.server:app",
        host=host,
        port=port,
        reload=reload,
    )
