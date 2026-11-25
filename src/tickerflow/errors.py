"""Exceptions raised by tickerflow."""

from __future__ import annotations


class ProviderError(Exception):
    """One provider could not serve the request; the message says why."""


class NoDataError(Exception):
    """No provider in the chain served the request.

    Attributes:
        symbol:   The symbol asked for.
        interval: The interval asked for.
        reasons:  Provider name → why it did not serve, in the order tried.
    """

    def __init__(self, symbol: str, interval: str, reasons: dict[str, str]) -> None:
        self.symbol = symbol
        self.interval = interval
        self.reasons = reasons
        detail = "; ".join(f"{name}: {why}" for name, why in reasons.items())
        super().__init__(
            f"no data for {symbol} {interval}: {detail or f'no provider supports {symbol}'}"
        )

    def __reduce__(self):  # pickle and copy rebuild it from its fields, not from the message
        return type(self), (self.symbol, self.interval, self.reasons)
