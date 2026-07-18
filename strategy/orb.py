"""Opening Range Breakout (ORB) — fewer, bigger intraday trades.

Idea: the first ~30 minutes set the day's initial range. A clean break above the
opening-range high, in the direction of the intraday trend (above VWAP), is a
higher-conviction signal than a generic 5-min breakout — so we take **at most one
trade per symbol per day**, aim for a **wide target** and let it run on a
**trailing stop**. This makes transaction costs trivial relative to the move and
fixes the payoff asymmetry that sinks tiny-target scalping.

Reuses the same `Strategy` contract, so the backtest engine, paper broker, and
live runner all work unchanged.
"""
from __future__ import annotations

from datetime import time

import pandas as pd

from config.settings import Settings, get_settings
from strategy.base import ExitRules, Strategy
from strategy.breakout import IST, _intraday_vwap, _parse_time

MARKET_OPEN = time(9, 15)


class OpeningRangeBreakout(Strategy):
    one_trade_per_day = True

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self.use_vwap_filter = s.use_vwap_filter
        # Opening range ends `opening_range_minutes` after the 09:15 open.
        end_min = 9 * 60 + 15 + s.opening_range_minutes
        self.or_end = time(end_min // 60, end_min % 60)
        self.entry_end = _parse_time(s.orb_entry_end)
        self._exit_rules = ExitRules(
            take_profit=s.orb_take_profit,
            stop_loss=s.orb_stop_loss,
            max_hold_bars=s.orb_max_hold_bars,
            trail=s.orb_trail,
        )

    @property
    def exit_rules(self) -> ExitRules:
        return self._exit_rules

    def _time_mask(self, index: pd.DatetimeIndex, cols, pred) -> pd.DataFrame:
        times = index.tz_convert(IST).time
        s = pd.Series([pred(t) for t in times], index=index)
        return pd.DataFrame({c: s for c in cols}, index=index)

    def entry_signals(
        self, close: pd.DataFrame, high: pd.DataFrame, volume: pd.DataFrame
    ) -> pd.DataFrame:
        day = close.index.normalize()

        # Opening-range high per day (max high during the OR window), broadcast to all bars.
        or_mask = self._time_mask(close.index, close.columns, lambda t: MARKET_OPEN <= t < self.or_end)
        or_high = high.where(or_mask).groupby(day).transform("max")

        # Break above OR high, inside the entry window, in the trend (above VWAP).
        in_window = self._time_mask(
            close.index, close.columns, lambda t: self.or_end <= t <= self.entry_end
        )
        signal = (close > or_high) & in_window
        if self.use_vwap_filter:
            signal &= close > _intraday_vwap(close, volume)
        signal = signal.fillna(False)

        # Keep only the first breakout of each day per symbol.
        first = signal & (signal.groupby(day).cumsum() == 1)
        return first

    def scan(self, bars: pd.DataFrame) -> bool:
        t_now = bars.index[-1].tz_convert(IST).time()
        if not (self.or_end <= t_now <= self.entry_end):
            return False
        times = bars.index.tz_convert(IST).time
        or_bars = bars[[MARKET_OPEN <= t < self.or_end for t in times]]
        if or_bars.empty:
            return False
        if bars["close"].iloc[-1] <= or_bars["high"].max():
            return False
        if self.use_vwap_filter:
            vwap = _intraday_vwap(bars["close"], bars["volume"]).iloc[-1]
            if bars["close"].iloc[-1] <= vwap:
                return False
        return True
