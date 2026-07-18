"""Strategy interface shared by the backtest and the live paper runner.

A strategy turns intraday OHLCV bars into **entry signals** plus the **exit
levels** (take-profit / stop-loss fractions) that govern each trade. The same
object drives both:

- Backtest: `entry_signals()` produces a boolean matrix over the full history.
- Live: `scan()` evaluates the most recent bar for one symbol at a time.

Exits (TP/SL/time-stop/square-off) are applied uniformly by the backtest engine
and the live runner, so they live as parameters here rather than per-strategy
code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ExitRules:
    """Per-trade exit parameters (fractions of entry price; bars for time-stop).

    When ``trail`` is True, ``stop_loss`` is treated as a *trailing* distance from
    the peak price since entry (lets winners run), and ``take_profit`` acts as an
    upper cap. When False, both are fixed levels off the entry price.
    """

    take_profit: float
    stop_loss: float
    max_hold_bars: int
    trail: bool = False


class Strategy(ABC):
    """Base class for intraday signal generators."""

    #: If True, at most one entry per symbol per day (e.g. opening-range breakout).
    one_trade_per_day: bool = False

    @property
    @abstractmethod
    def exit_rules(self) -> ExitRules:
        """Take-profit / stop-loss / time-stop applied to every trade."""

    @abstractmethod
    def entry_signals(
        self, close: pd.DataFrame, high: pd.DataFrame, volume: pd.DataFrame
    ) -> pd.DataFrame:
        """Boolean entry matrix aligned to the inputs (index=bars, columns=symbols).

        ``True`` where a long entry triggers on that bar for that symbol.
        Used by the vectorbt backtest across all symbols at once.
        """

    @abstractmethod
    def scan(self, bars: pd.DataFrame) -> bool:
        """Return True if the latest bar of a single symbol triggers an entry.

        ``bars`` is that symbol's recent OHLCV history (most recent row last).
        Used by the live paper runner per symbol.
        """
