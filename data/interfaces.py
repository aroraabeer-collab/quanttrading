"""Broker-agnostic market-data interface.

Strategy and backtest code depend only on ``DataProvider``, never on a concrete
broker SDK. Swapping data sources (Fyers -> another broker, or a cache-only
provider for tests) means implementing this ABC, nothing else.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Callable

import pandas as pd

# A quote callback receives (symbol, price, timestamp).
QuoteCallback = Callable[[str, float, pd.Timestamp], None]


class DataProvider(ABC):
    """Abstract source of historical bars and live quotes."""

    @abstractmethod
    def history(
        self,
        symbols: list[str],
        start: date,
        end: date,
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        """Historical OHLCV bars per symbol.

        Returns a mapping ``symbol -> DataFrame`` indexed by a tz-aware
        DatetimeIndex with columns ``[open, high, low, close, volume]``.
        """

    @abstractmethod
    def quote(self, symbols: list[str]) -> dict[str, float]:
        """Latest traded price per symbol (``symbol -> last price``)."""

    @abstractmethod
    def subscribe(self, symbols: list[str], callback: QuoteCallback) -> None:
        """Stream live quotes, invoking ``callback`` per tick. Blocks/threads
        depending on the implementation. Optional for backtest-only providers.
        """


class ProviderError(RuntimeError):
    """Raised when the underlying data source fails or is misconfigured."""
