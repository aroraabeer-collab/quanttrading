import pandas as pd

from execution.paper_broker import PaperBroker
from live.ml_trader import MLPaperTrader

IST = "Asia/Kolkata"
TS = pd.Timestamp("2026-07-13 10:00", tz=IST)


class _Quotes:
    def __init__(self, prices):
        self.prices = prices

    def quote(self, symbols):
        return {s: self.prices[s] for s in symbols if s in self.prices}

    def history(self, *a, **k):  # unused here
        return {}


def _trader(targets, prices, monkeypatch, tmp_path, top_k=2):
    # Persisted state is isolated globally by the autouse conftest fixture.
    provider = _Quotes(prices)
    broker = PaperBroker(1_000_000, slippage_bps=3.0, segment="delivery")
    trader = MLPaperTrader(provider, broker, top_k=top_k, horizon=5)
    monkeypatch.setattr(trader, "target_names", lambda: pd.Index(targets))
    return trader, broker


def test_rebalance_buys_target_names(monkeypatch, tmp_path):
    prices = {"NSE:AAA-EQ": 100.0, "NSE:BBB-EQ": 200.0}
    trader, broker = _trader(["NSE:AAA-EQ", "NSE:BBB-EQ"], prices, monkeypatch, tmp_path)
    trader.rebalance(TS)
    held = broker.positions()
    assert set(held) == {"NSE:AAA-EQ", "NSE:BBB-EQ"}
    # ~50% of ₹1,000,000 each -> ~5000 shares of AAA, ~2500 of BBB.
    assert abs(held["NSE:AAA-EQ"].qty - 5000) <= 5
    assert abs(held["NSE:BBB-EQ"].qty - 2500) <= 5


def test_rebalance_exits_dropped_names(monkeypatch, tmp_path):
    prices = {"NSE:AAA-EQ": 100.0, "NSE:BBB-EQ": 200.0, "NSE:CCC-EQ": 50.0}
    trader, broker = _trader(["NSE:AAA-EQ", "NSE:BBB-EQ"], prices, monkeypatch, tmp_path)
    trader.rebalance(TS)
    # Next rebalance drops BBB, adds CCC.
    monkeypatch.setattr(trader, "target_names", lambda: pd.Index(["NSE:AAA-EQ", "NSE:CCC-EQ"]))
    trader.rebalance(TS)
    held = broker.positions()
    assert set(held) == {"NSE:AAA-EQ", "NSE:CCC-EQ"}


def test_delivery_broker_charges_stt_both_sides():
    # Delivery STT (0.1% both sides) makes a flat round trip lose ~0.2%+.
    b = PaperBroker(1_000_000, slippage_bps=0.0, segment="delivery")
    from execution.interfaces import Side
    b.place_order("NSE:AAA-EQ", Side.BUY, 100, 500.0, TS)
    b.place_order("NSE:AAA-EQ", Side.SELL, 100, 500.0, TS)
    round_trip_cost = 1_000_000 - b.cash()
    assert round_trip_cost > 0.0015 * (100 * 500.0)  # >0.15% of turnover
