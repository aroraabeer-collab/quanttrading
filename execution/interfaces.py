"""Broker-agnostic execution interface.

The runner and portfolio code depend only on ``Broker``. `PaperBroker` simulates
fills for paper trading today; a future `FyersBroker` implementing the same ABC
places real orders with no changes upstream.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Fill:
    symbol: str
    side: Side
    qty: int
    price: float          # fill price incl. slippage
    cost: float           # ₹ transaction costs charged
    timestamp: pd.Timestamp


@dataclass
class Position:
    symbol: str
    qty: int = 0
    avg_price: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.qty != 0


@dataclass
class Order:
    symbol: str
    side: Side
    qty: int
    fill: Fill | None = field(default=None)


class Broker(ABC):
    """Abstract order interface."""

    @abstractmethod
    def place_order(
        self, symbol: str, side: Side, qty: int, price: float, timestamp: pd.Timestamp
    ) -> Order:
        """Submit an order at the given reference price; returns it with any fill."""

    @abstractmethod
    def positions(self) -> dict[str, Position]:
        """Current open positions keyed by symbol."""

    @abstractmethod
    def cash(self) -> float:
        """Available cash balance."""

    @abstractmethod
    def nav(self, marks: dict[str, float]) -> float:
        """Total account value = cash + positions marked at ``marks`` prices."""
