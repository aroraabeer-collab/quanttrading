"""Paper broker — simulates fills against a reference price.

Mirrors the backtest's cost treatment so paper P&L is comparable: slippage is
applied as **price impact** (buys fill up, sells fill down) and statutory +
brokerage costs are **charged as ₹** on each fill. Long-only (cash-segment
scalper); sells close existing longs. State can be persisted to disk.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backtest.costs import DeliveryCostModel, IntradayCostModel
from config.settings import STATE_DIR
from execution.interfaces import Broker, Fill, Order, Position, Side


class PaperBroker(Broker):
    def __init__(
        self, initial_cash: float, slippage_bps: float, segment: str = "intraday"
    ) -> None:
        self._cash = initial_cash
        self._slip = slippage_bps / 1e4
        # Statutory/brokerage only — slippage is handled via fill price, not double-charged.
        self._statutory = (
            DeliveryCostModel(slippage_bps=0.0) if segment == "delivery"
            else IntradayCostModel(slippage_bps=0.0)
        )
        self._positions: dict[str, Position] = {}
        self.fills: list[Fill] = []
        self.realized_pnl: float = 0.0

    # --- Broker interface --------------------------------------------------
    def place_order(
        self, symbol: str, side: Side, qty: int, price: float, timestamp: pd.Timestamp
    ) -> Order:
        if qty <= 0:
            raise ValueError("qty must be positive")
        side = Side(side)
        fill_price = price * (1 + self._slip) if side is Side.BUY else price * (1 - self._slip)
        value = qty * fill_price
        cost = self._statutory.side_cost(value, side.value)

        if side is Side.BUY:
            self._cash -= value + cost
            self._apply_buy(symbol, qty, fill_price)
        else:
            self._cash += value - cost
            self._apply_sell(symbol, qty, fill_price, cost)

        fill = Fill(symbol, side, qty, fill_price, cost, timestamp)
        self.fills.append(fill)
        return Order(symbol=symbol, side=side, qty=qty, fill=fill)

    def positions(self) -> dict[str, Position]:
        return {s: p for s, p in self._positions.items() if p.is_open}

    def cash(self) -> float:
        return self._cash

    def nav(self, marks: dict[str, float]) -> float:
        pos_value = sum(
            p.qty * marks.get(s, p.avg_price) for s, p in self.positions().items()
        )
        return self._cash + pos_value

    # --- internals ---------------------------------------------------------
    def _apply_buy(self, symbol: str, qty: int, price: float) -> None:
        pos = self._positions.setdefault(symbol, Position(symbol))
        total_qty = pos.qty + qty
        pos.avg_price = (pos.qty * pos.avg_price + qty * price) / total_qty
        pos.qty = total_qty

    def _apply_sell(self, symbol: str, qty: int, price: float, cost: float) -> None:
        pos = self._positions.get(symbol)
        if pos is None or pos.qty < qty:
            raise ValueError(f"Cannot sell {qty} {symbol}; holding {pos.qty if pos else 0}")
        self.realized_pnl += qty * (price - pos.avg_price) - cost
        pos.qty -= qty
        if pos.qty == 0:
            pos.avg_price = 0.0

    # --- persistence -------------------------------------------------------
    def load_state(self, path: Path | None = None) -> bool:
        """Restore cash/positions/realized P&L from disk; False if no state file."""
        path = path or (STATE_DIR / "paper_state.json")
        if not path.exists():
            return False
        d = json.loads(path.read_text())
        self._cash = d["cash"]
        self.realized_pnl = d.get("realized_pnl", 0.0)
        self._positions = {
            s: Position(s, v["qty"], v["avg_price"]) for s, v in d.get("positions", {}).items()
        }
        return True

    def save_state(self, path: Path | None = None) -> Path:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        path = path or (STATE_DIR / "paper_state.json")
        path.write_text(
            json.dumps(
                {
                    "cash": self._cash,
                    "realized_pnl": self.realized_pnl,
                    "positions": {
                        s: {"qty": p.qty, "avg_price": p.avg_price}
                        for s, p in self.positions().items()
                    },
                    "num_fills": len(self.fills),
                },
                indent=2,
            )
        )
        return path
