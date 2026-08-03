"""Tiingo OHLCV provider — daily and weekly bars for stocks and ETFs.

Requires a free Tiingo API key: https://www.tiingo.com/account/api/token
Set the ``TIINGO_API_KEY`` environment variable before use.
"""

from __future__ import annotations

import asyncio
import datetime
import os
import re

import requests

from tickerflow.models import Candle
from tickerflow.providers.base import OHLCVProvider

_BASE_URL = "https://api.tiingo.com/tiingo/daily"

# Tiingo only offers daily/weekly resolution on its free daily endpoint
_RESAMPLE: dict[str, str] = {
    "1d": "daily",
    "1w": "weekly",
}

_BAR_DURATION: dict[str, datetime.timedelta] = {
    "1d": datetime.timedelta(days=1),
    "1w": datetime.timedelta(weeks=1),
}
# Tiingo covers US-listed stocks and ETFs: 1-5 uppercase letters, or exchange-suffixed
_STOCK_RE     = re.compile(r"^[A-Z]{1,5}$")
_INTL_STOCK_RE = re.compile(r"^[A-Z0-9]{1,7}\.[A-Z]{1,3}$")


class TiingoProvider(OHLCVProvider):
    """Fetches daily and weekly OHLCV bars from the Tiingo REST API.

    Supports US stocks and ETFs. Intraday intervals (1m, 5m, 1h …) are not
    available on the free tier and return ``None``.

    An API key is required. If ``TIINGO_API_KEY`` is not set the provider
    raises ``RuntimeError`` at fetch time rather than silently returning empty
    data, so the caller knows the root cause immediately.
    """

    name = "tiingo"

    def supports(self, symbol: str) -> bool:
        up = symbol.upper()
        return bool(_STOCK_RE.match(up) or _INTL_STOCK_RE.match(up))

    async def fetch(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> list[Candle] | None:
        resample = _RESAMPLE.get(interval)
        if resample is None:
            return None  # intraday not supported

        api_key = os.getenv("TIINGO_API_KEY")
        if not api_key:
            raise RuntimeError(
                "TIINGO_API_KEY environment variable is not set. "
                "Get a free key at https://www.tiingo.com/account/api/token"
            )

        bar_delta = _BAR_DURATION[interval]
        start = datetime.datetime.now(datetime.UTC) - bar_delta * int(limit * 1.2 + 5)

        ticker = symbol.upper()
        rows = await asyncio.to_thread(
            self._download, ticker, resample, start, api_key
        )
        if not rows:
            return None

        candles: list[Candle] = []
        for row in rows[-limit:]:
            try:
                ts = datetime.datetime.fromisoformat(row["date"])
                candles.append(
                    Candle(
                        time=int(ts.timestamp()),
                        open=float(row.get("adjOpen") or row["open"]),
                        high=float(row.get("adjHigh") or row["high"]),
                        low=float(row.get("adjLow") or row["low"]),
                        close=float(row.get("adjClose") or row["close"]),
                        volume=float(row.get("adjVolume") or row.get("volume") or 0.0),
                    )
                )
            except (KeyError, ValueError):
                continue

        return candles or None

    @staticmethod
    def _download(
        ticker: str,
        resample: str,
        start: datetime.datetime,
        api_key: str,
    ) -> list[dict] | None:
        """Blocking Tiingo request — called via asyncio.to_thread."""
        url = f"{_BASE_URL}/{ticker}/prices"
        headers = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        }
        params = {
            "startDate": start.strftime("%Y-%m-%d"),
            "resampleFreq": resample,
            "format": "json",
        }
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data if isinstance(data, list) else None
        except Exception:  # noqa: BLE001
            return None
