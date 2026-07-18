"""Intraday breakout scanner for the Nifty 50, with quality filters.

Base entry (long): the current bar's close breaks **above the high of the
previous `lookback` bars**, confirmed by a volume surge (current volume above
`volume_mult` × the average volume of those prior bars).

Quality filters (trade less, but better) — both configurable:
  - **VWAP trend filter:** only enter when price is above the day's VWAP, i.e.
    trade with the intraday trend rather than into it.
  - **Time-of-day window:** only enter during the morning momentum window
    (default 09:20–11:00 IST), skipping low-conviction midday chop.

Each trade then exits on a small take-profit / stop / time-stop (engine/runner),
squared off by end of day. Same logic drives the backtest (`entry_signals`,
vectorized across all symbols) and the live runner (`scan`, one symbol's latest
bar).
"""
from __future__ import annotations

from datetime import time

import pandas as pd

from config.settings import Settings, get_settings
from strategy.base import ExitRules, Strategy

IST = "Asia/Kolkata"


def _parse_time(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def _intraday_vwap(close: pd.DataFrame | pd.Series, volume: pd.DataFrame | pd.Series):
    """Cumulative VWAP that resets each trading day (uses close as typical price)."""
    day = close.index.normalize()
    cum_pv = (close * volume).groupby(day).cumsum()
    cum_v = volume.groupby(day).cumsum()
    return cum_pv / cum_v


class BreakoutScanner(Strategy):
    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self.lookback = s.breakout_lookback
        self.volume_mult = s.volume_mult
        self.use_vwap_filter = s.use_vwap_filter
        self.window_start = _parse_time(s.entry_window_start)
        self.window_end = _parse_time(s.entry_window_end)
        self._exit_rules = ExitRules(
            take_profit=s.take_profit,
            stop_loss=s.stop_loss,
            max_hold_bars=s.max_hold_bars,
        )

    @property
    def exit_rules(self) -> ExitRules:
        return self._exit_rules

    def _in_window(self, t: time) -> bool:
        return self.window_start <= t <= self.window_end

    def entry_signals(
        self, close: pd.DataFrame, high: pd.DataFrame, volume: pd.DataFrame
    ) -> pd.DataFrame:
        # Base breakout + volume confirmation.
        prior_high = high.rolling(self.lookback).max().shift(1)
        avg_vol = volume.rolling(self.lookback).mean().shift(1)
        signal = (close > prior_high) & (volume > self.volume_mult * avg_vol)

        # VWAP trend filter.
        if self.use_vwap_filter:
            signal &= close > _intraday_vwap(close, volume)

        # Time-of-day window filter.
        times = close.index.tz_convert(IST).time
        in_window = pd.Series([self._in_window(t) for t in times], index=close.index)
        in_window_mask = pd.DataFrame(
            {c: in_window for c in close.columns}, index=close.index
        )
        signal = signal & in_window_mask

        return signal.fillna(False)

    def scan(self, bars: pd.DataFrame) -> bool:
        if len(bars) < self.lookback + 1:
            return False
        if not self._in_window(bars.index[-1].tz_convert(IST).time()):
            return False

        window = bars.iloc[-(self.lookback + 1):]
        prior = window.iloc[:-1]      # previous `lookback` bars
        current = window.iloc[-1]      # bar being evaluated
        if current["close"] <= prior["high"].max():
            return False
        if current["volume"] <= self.volume_mult * prior["volume"].mean():
            return False
        if self.use_vwap_filter:
            vwap = _intraday_vwap(bars["close"], bars["volume"]).iloc[-1]
            if current["close"] <= vwap:
                return False
        return True
