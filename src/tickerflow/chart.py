"""Terminal candlestick charts — pure stdlib, ANSI colors.

Renders an OHLC candlestick chart with a volume pane below,
green/red coloring, and a date x-axis. Zero third-party plotting dependencies.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

from tickerflow.models import Candle

_RESET, _DIM = "\033[0m", "\033[2m"
_GREEN, _RED = "\033[32m", "\033[31m"
_BODY, _WICK, _VOL = "█", "│", "█"
MAX_COLS = 60


def _color() -> bool:
    return not (os.getenv("NO_COLOR") or os.getenv("TICKERFLOW_NO_COLOR")) and sys.stdout.isatty()


def _p(text: str, code: str, on: bool) -> str:
    return f"{code}{text}{_RESET}" if on else text


def _fmt(p: float) -> str:
    return f"{p:,.0f}" if p >= 1000 else (f"{p:,.2f}" if p >= 1 else f"{p:.4f}")


def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%d/%m")


def render(
    candles: list[Candle],
    symbol: str = "",
    interval: str = "",
    height: int = 18,
    color: bool | None = None,
) -> str:
    """Render an OHLC candlestick chart with volume pane as a string."""
    if not candles:
        return f"No candles to chart for {symbol}."
    on = _color() if color is None else color

    # Downsample very long series so it fits a terminal
    if len(candles) > MAX_COLS:
        step = len(candles) / MAX_COLS
        candles = [candles[int(i * step)] for i in range(MAX_COLS)]
    n = len(candles)

    lo, hi = min(c.low for c in candles), max(c.high for c in candles)
    pad = (hi - lo) * 0.05 or hi * 0.01 or 1
    lo, hi = lo - pad, hi + pad
    rows = height
    axis_w = max(len(_fmt(hi)), len(_fmt(lo))) + 1

    def row(price: float) -> int:  # 0 = top
        return int(round((hi - price) / (hi - lo) * (rows - 1)))

    grid = [[" "] * n for _ in range(rows)]
    codes = [[""] * n for _ in range(rows)]
    for i, c in enumerate(candles):
        up = c.close >= c.open
        r_hi, r_lo, r_o, r_c = row(c.high), row(c.low), row(c.open), row(c.close)
        b_top, b_bot = min(r_o, r_c), max(r_o, r_c)
        code = _GREEN if up else _RED
        for r in range(rows):
            if b_top <= r <= b_bot:
                grid[r][i], codes[r][i] = _BODY, code
            elif r_hi <= r <= r_lo:
                grid[r][i], codes[r][i] = _WICK, _DIM

    title_parts = [symbol.upper(), interval]
    title_str = " · ".join(p for p in title_parts if p)
    header = f"{title_str} · {n} candles" if title_str else f"{n} candles"
    out = [header]

    ticks = {0, rows // 4, rows // 2, (3 * rows) // 4, rows - 1}
    for r in range(rows):
        label = _fmt(hi - (r / (rows - 1)) * (hi - lo)).rjust(axis_w) if r in ticks else " " * axis_w
        line = _p(label, _DIM, on) + " "
        line += "".join(_p(grid[r][i], codes[r][i], on) if grid[r][i] != " " else " " for i in range(n))
        out.append(line)

    # Volume pane (vertical bars, colored by direction)
    vol_rows = 4
    max_vol = max((c.volume for c in candles), default=0) or 1
    out.append(_p(" " * axis_w + " ┼" + "─" * n, _DIM, on))
    for r in range(vol_rows):
        line = _p("vol".rjust(axis_w) if r == 0 else " " * axis_w, _DIM, on) + " "
        for i, c in enumerate(candles):
            h = min(int(round(c.volume / max_vol * vol_rows)), vol_rows)
            filled = r >= vol_rows - h
            line += _p(_VOL, _GREEN if c.close >= c.open else _RED, on) if filled else " "
        out.append(line)

    # Date x-axis (first / mid / last, skip on overlap)
    xs = [" "] * n

    def put(idx: int, text: str) -> None:
        for j, ch in enumerate(text):
            if 0 <= idx + j < n and xs[idx + j] == " ":
                xs[idx + j] = ch

    put(0, _date(candles[0].time))
    put((n - 1) // 2 - 2, _date(candles[(n - 1) // 2].time))
    put(n - 5, _date(candles[-1].time))
    out.append(_p(" " * (axis_w + 1) + "".join(xs), _DIM, on))
    return "\n".join(out)


def render_chart(
    candles: list[Candle],
    symbol: str = "",
    interval: str = "",
) -> None:
    """Print the rendered candlestick chart to stdout."""
    print(render(candles, symbol=symbol, interval=interval))
