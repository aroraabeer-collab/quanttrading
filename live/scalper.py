"""Autonomous intraday share scalper (paper) — a learning tool.

Buys small dips and sells small rips across a few liquid stocks, many times a
day, using the real intraday cost model. Its PURPOSE is to make the cost drain
*visible*: the daemon shows GROSS P&L (before costs) next to NET (after), so you
watch transaction costs eat the gross with every round trip. This is the
approach the project proved loses — running it on paper drives that home.
"""
from __future__ import annotations

import pandas as pd

from data.interfaces import DataProvider
from execution.interfaces import Broker, Side
from portfolio.sizing import size_trade


class ScalperPaperTrader:
    def __init__(
        self,
        provider: DataProvider,
        broker: Broker,
        symbols: list[str],
        capital_per_trade: float = 0.02,   # 2% of NAV per small trade
        entry_dev: float = 0.001,          # buy when price dips 0.1% below the fast EMA
        target: float = 0.0015,            # take a 0.15% scalp profit
        stop: float = 0.0015,              # cut a 0.15% loss
        ema_span: int = 5,
        square_off: str = "15:15",
    ) -> None:
        self.provider = provider
        self.broker = broker
        self.symbols = symbols
        self.cpt = capital_per_trade
        self.entry_dev = entry_dev
        self.target = target
        self.stop = stop
        self.ema_span = ema_span
        self.square_off = square_off

    def step(self, now: pd.Timestamp | None = None) -> dict:
        now = now or pd.Timestamp.now(tz="Asia/Kolkata")
        bars = self.provider.history(self.symbols, now.date(), now.date(), "1")
        quotes = self.provider.quote(self.symbols)
        nav = self.broker.nav(quotes)
        past_squareoff = now.strftime("%H:%M") >= self.square_off
        log = {"time": now, "buys": 0, "sells": 0}

        # 1) Manage exits — tiny target / stop, and force-flat near close.
        for sym, pos in list(self.broker.positions().items()):
            price = quotes.get(sym)
            if not price:
                continue
            e = pos.avg_price
            if price >= e * (1 + self.target) or price <= e * (1 - self.stop) or past_squareoff:
                self.broker.place_order(sym, Side.SELL, pos.qty, price, now)
                log["sells"] += 1

        # 2) Enter — buy a small dip below the fast EMA (unless near close).
        if not past_squareoff:
            for sym in self.symbols:
                if sym in self.broker.positions():
                    continue
                b = bars.get(sym)
                if b is None or len(b) < self.ema_span + 1:
                    continue
                ema = b["close"].ewm(span=self.ema_span).mean().iloc[-1]
                price = quotes.get(sym)
                if not price:
                    continue
                if price < ema * (1 - self.entry_dev):
                    qty = size_trade(nav, price, self.cpt)
                    if qty > 0:
                        self.broker.place_order(sym, Side.BUY, qty, price, now)
                        log["buys"] += 1
        return log
