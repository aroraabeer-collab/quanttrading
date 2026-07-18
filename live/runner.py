"""Intraday paper-trading runner.

Every bar interval during NSE hours it: (1) fetches recent bars + quotes for all
Nifty 50 names, (2) manages open positions against target / stop / time-stop /
square-off, then (3) scans flat names for fresh breakouts and opens paper
positions subject to the risk gate. All simulated — no real orders.
"""
from __future__ import annotations

import time as _time
from datetime import date

import pandas as pd

from config.settings import Settings, get_settings
from config.universe import nifty50_symbols
from data.interfaces import DataProvider
from execution.interfaces import Broker, Position, Side
from live.clock import MarketClock
from portfolio.risk import RiskManager
from portfolio.sizing import size_trade
from strategy.base import Strategy


class PaperRunner:
    def __init__(
        self,
        provider: DataProvider,
        broker: Broker,
        strategy: Strategy,
        settings: Settings | None = None,
        clock: MarketClock | None = None,
    ) -> None:
        self.provider = provider
        self.broker = broker
        self.strategy = strategy
        self.s = settings or get_settings()
        self.clock = clock or MarketClock(self.s)
        self.symbols = nifty50_symbols()
        self.resolution = self.s.bar_resolution
        self._bar_minutes = int(self.resolution)
        self.entry_time: dict[str, pd.Timestamp] = {}
        self.peak_price: dict[str, float] = {}       # for trailing stops
        self.traded_today: set[str] = set()          # for one-trade-per-day strategies
        self.risk: RiskManager | None = None
        self._risk_day: date | None = None

    # --- one scan/manage cycle (unit-testable) -----------------------------
    def run_once(self, now: pd.Timestamp | None = None) -> dict:
        now = now or self.clock.now()
        bars = self.provider.history(self.symbols, now.date(), now.date(), self.resolution)
        quotes = self.provider.quote(self.symbols)
        nav = self.broker.nav(quotes)
        self._ensure_risk(now, nav)
        log: dict = {"time": now, "nav": nav, "entries": [], "exits": []}

        # 1) Manage open positions.
        for sym, pos in list(self.broker.positions().items()):
            price = quotes.get(sym)
            if price is None:
                continue
            self.peak_price[sym] = max(self.peak_price.get(sym, price), price)
            reason = self._exit_reason(sym, pos, price, now)
            if reason:
                self.broker.place_order(sym, Side.SELL, pos.qty, price, now)
                self.entry_time.pop(sym, None)
                self.peak_price.pop(sym, None)
                log["exits"].append((sym, reason, price))

        # 2) Scan flat names for new entries (unless past square-off).
        if not self.clock.past_square_off(now):
            for sym in self.symbols:
                if sym in self.broker.positions():
                    continue
                if self.strategy.one_trade_per_day and sym in self.traded_today:
                    continue
                b = bars.get(sym)
                if b is None or b.empty or not self.strategy.scan(b):
                    continue
                nav = self.broker.nav(quotes)
                ok, reason = self.risk.can_enter(len(self.broker.positions()), nav)
                if not ok:
                    break  # portfolio-level limit reached; stop scanning this cycle
                price = quotes.get(sym)
                if price is None:
                    continue
                qty = size_trade(nav, price, self.s.capital_per_trade)
                if qty <= 0:
                    continue
                order = self.broker.place_order(sym, Side.BUY, qty, price, now)
                self.entry_time[sym] = now
                self.peak_price[sym] = order.fill.price
                self.traded_today.add(sym)
                self.risk.record_entry()
                log["entries"].append((sym, qty, price))

        if hasattr(self.broker, "save_state"):
            self.broker.save_state()
        return log

    def _exit_reason(
        self, sym: str, pos: Position, price: float, now: pd.Timestamp
    ) -> str | None:
        e = pos.avg_price
        rules = self.strategy.exit_rules
        if price >= e * (1 + rules.take_profit):
            return "target"
        if rules.trail:
            peak = self.peak_price.get(sym, e)
            if price <= peak * (1 - rules.stop_loss):
                return "trail-stop"
        elif price <= e * (1 - rules.stop_loss):
            return "stop"
        entry = self.entry_time.get(sym)
        if entry is not None:
            bars_held = (now - entry).total_seconds() / 60 / self._bar_minutes
            if bars_held >= rules.max_hold_bars:
                return "time-stop"
        if self.clock.past_square_off(now):
            return "square-off"
        return None

    def _ensure_risk(self, now: pd.Timestamp, nav: float) -> None:
        today = now.date()
        if self.risk is None or self._risk_day != today:
            self.risk = RiskManager(day_start_nav=nav, settings=self.s)
            self._risk_day = today
            self.entry_time.clear()
            self.peak_price.clear()
            self.traded_today.clear()

    # --- live loop ---------------------------------------------------------
    def run(self, poll_seconds: float | None = None) -> None:
        interval = poll_seconds or self._bar_minutes * 60
        print(f"Paper runner started — {len(self.symbols)} symbols @ {self.resolution}m bars.")
        while True:
            now = self.clock.now()
            if not self.clock.is_open(now):
                _time.sleep(30)
                continue
            self._print_log(self.run_once(now))
            _time.sleep(interval)

    @staticmethod
    def _print_log(log: dict) -> None:
        ts = log["time"].strftime("%H:%M:%S")
        for sym, reason, price in log["exits"]:
            print(f"[{ts}] EXIT  {sym:<18} @ {price:>9.2f}  ({reason})")
        for sym, qty, price in log["entries"]:
            print(f"[{ts}] ENTER {sym:<18} x{qty:<5} @ {price:>9.2f}")
        if log["entries"] or log["exits"]:
            print(f"[{ts}] NAV ₹{log['nav']:,.0f}")
