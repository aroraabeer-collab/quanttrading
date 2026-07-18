"""Intraday mean-reversion — buy dips back toward VWAP.

Opposite thesis to momentum: intraday large-caps often *overreact*, so a sharp
push **below** VWAP tends to snap back. Long-only (cash segment), so we only take
the buy-the-dip side.

Entry (long): price is stretched more than `mr_entry_dev` **below** the day's
VWAP AND the current bar ticks up (close > previous close) — a reversal signal
that avoids catching a falling knife. Exit: a small take-profit as it reverts,
a stop if the fall continues, a time-stop, or square-off.

Reuses the `Strategy` contract, so the engine, paper broker, and runner are
unchanged.
"""
from __future__ import annotations

import pandas as pd

from config.settings import Settings, get_settings
from strategy.base import ExitRules, Strategy
from strategy.breakout import IST, _intraday_vwap, _parse_time


class MeanReversion(Strategy):
    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self.entry_dev = s.mr_entry_dev
        self.window_start = _parse_time(s.mr_window_start)
        self.window_end = _parse_time(s.mr_window_end)
        self._exit_rules = ExitRules(
            take_profit=s.mr_take_profit,
            stop_loss=s.mr_stop_loss,
            max_hold_bars=s.mr_max_hold_bars,
        )

    @property
    def exit_rules(self) -> ExitRules:
        return self._exit_rules

    def _in_window(self, t) -> bool:
        return self.window_start <= t <= self.window_end

    def entry_signals(
        self, close: pd.DataFrame, high: pd.DataFrame, volume: pd.DataFrame
    ) -> pd.DataFrame:
        vwap = _intraday_vwap(close, volume)
        below = (vwap - close) / vwap > self.entry_dev   # stretched below VWAP
        tick_up = close > close.shift(1)                 # reversal confirmation
        signal = below & tick_up

        times = close.index.tz_convert(IST).time
        in_window = pd.Series([self._in_window(t) for t in times], index=close.index)
        in_window_mask = pd.DataFrame(
            {c: in_window for c in close.columns}, index=close.index
        )
        return (signal & in_window_mask).fillna(False)

    def scan(self, bars: pd.DataFrame) -> bool:
        if len(bars) < 2:
            return False
        if not self._in_window(bars.index[-1].tz_convert(IST).time()):
            return False
        vwap = _intraday_vwap(bars["close"], bars["volume"]).iloc[-1]
        close = bars["close"].iloc[-1]
        if (vwap - close) / vwap <= self.entry_dev:
            return False
        return bool(close > bars["close"].iloc[-2])
