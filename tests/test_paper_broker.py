import pandas as pd

from execution.interfaces import Side
from execution.paper_broker import PaperBroker

TS = pd.Timestamp("2026-01-05 10:00", tz="Asia/Kolkata")


def test_buy_reduces_cash_and_opens_position():
    b = PaperBroker(initial_cash=1_000_000, slippage_bps=0.0)
    b.place_order("NSE:AAA-EQ", Side.BUY, qty=100, price=500.0, timestamp=TS)
    pos = b.positions()["NSE:AAA-EQ"]
    assert pos.qty == 100
    assert pos.avg_price == 500.0
    # Cash drops by notional + costs.
    assert b.cash() < 1_000_000 - 100 * 500.0


def test_slippage_moves_fill_price():
    b = PaperBroker(initial_cash=1_000_000, slippage_bps=10.0)  # 0.10%
    order = b.place_order("NSE:AAA-EQ", Side.BUY, 10, 1000.0, TS)
    assert order.fill.price == 1000.0 * (1 + 0.001)  # buys fill up


def test_round_trip_pnl_is_negative_after_costs_when_flat():
    b = PaperBroker(initial_cash=1_000_000, slippage_bps=3.0)
    b.place_order("NSE:AAA-EQ", Side.BUY, 100, 500.0, TS)
    b.place_order("NSE:AAA-EQ", Side.SELL, 100, 500.0, TS)  # exit at same price
    # No open positions; costs + slippage make a flat round trip a small loss.
    assert b.positions() == {}
    assert b.realized_pnl < 0
    assert b.nav({}) < 1_000_000


def test_cannot_oversell():
    b = PaperBroker(initial_cash=1_000_000, slippage_bps=0.0)
    b.place_order("NSE:AAA-EQ", Side.BUY, 10, 100.0, TS)
    try:
        b.place_order("NSE:AAA-EQ", Side.SELL, 20, 100.0, TS)
    except ValueError:
        return
    raise AssertionError("expected ValueError on overselling")
