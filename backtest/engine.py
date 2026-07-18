"""Intraday backtest engine built on vectorbt.

Runs the breakout scanner across all Nifty 50 columns at once using
`Portfolio.from_signals`, with take-profit / stop-loss handled intrabar and a
forced end-of-day square-off (no overnight positions). One shared cash pool
models a single trading account, so simultaneous signals compete for capital.

Note: the discrete `max_hold_bars` time-stop is enforced live; in the backtest
it is approximated by TP/SL plus the square-off, which is a close proxy given
the tight (+0.4% / -0.2%) exits. This is documented as a known simplification.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pandas as pd
import vectorbt as vbt

from backtest.costs import IntradayCostModel
from config.settings import Settings, get_settings
from strategy.base import Strategy


@dataclass
class Panels:
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame


def build_panels(bars: dict[str, pd.DataFrame]) -> Panels:
    """Assemble aligned wide OHLCV frames (index=timestamp, columns=symbols)."""
    fields = {f: {} for f in ["open", "high", "low", "close", "volume"]}
    for sym, df in bars.items():
        if df is None or df.empty:
            continue
        for f in fields:
            fields[f][sym] = df[f]
    panels = {f: pd.DataFrame(cols).sort_index() for f, cols in fields.items()}
    # Align all fields to a common index; forward-fill within the trading day only.
    common = panels["close"].dropna(how="all").index
    return Panels(**{f: panels[f].reindex(common) for f in panels})


def _parse_time(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def _freq_from_resolution(resolution: str) -> str:
    return f"{int(resolution)}min"


def run_backtest(
    bars: dict[str, pd.DataFrame],
    strategy: Strategy,
    settings: Settings | None = None,
) -> vbt.Portfolio:
    s = settings or get_settings()
    panels = build_panels(bars)
    if panels.close.empty:
        raise ValueError("No bar data to backtest — run scripts/download_data.py first.")

    entries = strategy.entry_signals(panels.close, panels.high, panels.volume)

    # Square-off: force flat at/after the cutoff and block new entries near close.
    cutoff = _parse_time(s.square_off_time)
    bar_times = panels.close.index.tz_convert("Asia/Kolkata").time
    after_cutoff = pd.Series(
        [t >= cutoff for t in bar_times], index=panels.close.index
    )
    exits = pd.DataFrame(
        {c: after_cutoff for c in panels.close.columns}, index=panels.close.index
    )
    entries = entries & ~exits.values

    notional = s.capital_per_trade * s.initial_capital
    costs = IntradayCostModel(s.slippage_bps)

    return vbt.Portfolio.from_signals(
        close=panels.close,
        entries=entries,
        exits=exits,
        open=panels.open,
        high=panels.high,
        low=panels.low,
        tp_stop=strategy.exit_rules.take_profit,
        sl_stop=strategy.exit_rules.stop_loss,
        sl_trail=strategy.exit_rules.trail,
        size=notional,
        size_type="value",
        fees=costs.per_side_fee_fraction(notional),
        slippage=costs.slippage_fraction(),
        init_cash=s.initial_capital,
        cash_sharing=True,
        group_by=True,
        freq=_freq_from_resolution(s.bar_resolution),
    )
