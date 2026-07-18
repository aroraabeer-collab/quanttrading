"""Performance reporting for a completed backtest.

`summary` prints headline stats **plus an explicit per-trade cost breakdown** so
the cost drag is never hidden. `tearsheet` writes a quantstats HTML report.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless — no GUI needed for report generation

import pandas as pd
import vectorbt as vbt

from backtest.costs import IntradayCostModel
from config.settings import REPORTS_DIR, Settings, get_settings


def _daily_returns(pf: vbt.Portfolio) -> pd.Series:
    """Portfolio equity resampled to daily returns (for quantstats)."""
    value = pf.value()
    if isinstance(value, pd.DataFrame):  # grouped portfolio -> single column
        value = value.iloc[:, 0]
    daily = value.resample("1D").last().dropna()
    return daily.pct_change().dropna()


def summary(pf: vbt.Portfolio, settings: Settings | None = None) -> dict:
    """Print and return headline stats + the modelled per-trade cost."""
    s = settings or get_settings()
    stats = pf.stats()

    def g(key, default=None):
        try:
            return stats[key]
        except (KeyError, TypeError):
            return default

    notional = s.capital_per_trade * s.initial_capital
    cost = IntradayCostModel(s.slippage_bps).round_trip(notional)

    print("\n=== Backtest summary ===")
    print(f"Total return:      {g('Total Return [%]'):.2f}%")
    print(f"Max drawdown:      {g('Max Drawdown [%]'):.2f}%")
    print(f"Sharpe ratio:      {g('Sharpe Ratio'):.2f}")
    print(f"Total trades:      {int(g('Total Trades', 0))}")
    print(f"Win rate:          {g('Win Rate [%]', float('nan')):.2f}%")
    print(f"Avg winning trade: {g('Avg Winning Trade [%]', float('nan')):.3f}%")
    print(f"Avg losing trade:  {g('Avg Losing Trade [%]', float('nan')):.3f}%")

    print(f"\n=== Round-trip cost @ ₹{notional:,.0f} notional ===")
    for k, v in cost.as_dict().items():
        unit = "bps" if k == "total_bps" else "₹"
        print(f"  {k:<14} {unit} {v:,.2f}")
    print(
        f"\n  Cost floor per trade: {cost.total_fraction*1e2:.3f}% "
        f"(TP is {s.take_profit*1e2:.2f}% — the edge must clear this on every trade)"
    )
    return {"stats": stats, "cost": cost}


def tearsheet(
    pf: vbt.Portfolio,
    output: Path | None = None,
    benchmark: pd.Series | None = None,
) -> Path:
    """Write a quantstats HTML tearsheet; returns the output path."""
    import quantstats as qs

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output = output or (REPORTS_DIR / "backtest_report.html")
    returns = _daily_returns(pf)
    qs.reports.html(
        returns,
        benchmark=benchmark,
        output=str(output),
        title="Nifty 50 Intraday Breakout — Backtest",
    )
    print(f"\nTearsheet written to {output}")
    return output
