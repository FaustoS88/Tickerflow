"""Terminal chart rendering for OHLCV data using plotext.

Usage:
    from tickerflow.chart import render_chart
    render_chart(candles, symbol="BTCUSDT", interval="1d")

Or via CLI:
    tickerflow chart BTCUSDT 1d 30
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tickerflow.models import Candle


def render_chart(
    candles: list[Candle],
    symbol: str = "",
    interval: str = "",
) -> None:
    """Render a terminal chart of OHLCV candles using plotext.

    Displays a price line chart (close prices) with high/low bands and
    a volume bar subplot below. Green for up candles, red for down.

    Raises ImportError with an install hint if plotext is not available.
    """
    try:
        import plotext as plt  # noqa: PLC0415
    except ImportError:
        raise ImportError(
            "plotext is required for terminal charts. "
            "Install it with: pip install tickerflow[chart]"
        ) from None

    if not candles:
        print("No candle data to chart.")
        return

    # Prepare data
    dates = [
        datetime.fromtimestamp(c.time, tz=timezone.utc).strftime("%m/%d")
        for c in candles
    ]
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]

    # Color each bar: green if close >= open, red otherwise
    bar_colors = [
        "green" if c.close >= c.open else "red"
        for c in candles
    ]

    # Determine if volume data is meaningful (not all zeros)
    has_volume = any(v > 0 for v in volumes)

    if has_volume:
        plt.subplots(2, 1)

        # --- Price subplot ---
        plt.subplot(1, 1)

    plt.theme("dark")
    plt.plot(dates, highs, color="gray", label="High")
    plt.plot(dates, closes, color="cyan", label="Close", marker="braille")
    plt.plot(dates, lows, color="gray", label="Low")

    title = " ".join(filter(None, [symbol.upper(), interval.upper()]))
    plt.title(title or "OHLCV Chart")
    plt.xlabel("")

    if has_volume:
        # --- Volume subplot ---
        plt.subplot(2, 1)
        plt.theme("dark")
        plt.bar(dates, volumes, color=bar_colors, label="Volume")
        plt.title("Volume")
        plt.xlabel("")

    plt.show()
