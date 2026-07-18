"""Backtest systematic NIFTY option selling (volatility risk premium).

    uv run scripts/run_options.py

Model-based (Black-Scholes priced at India VIX), since expired option quotes
aren't available from Fyers. Compares a naked short strangle, the same with a
stop-loss, and a defined-risk iron condor — to show the win-rate vs tail-risk
tradeoff honestly.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

import pandas as pd

from config.settings import CACHE_DIR
from data.fyers_provider import FyersProvider
from options.vol_backtest import MARGIN_PER_LOT, run_vol_backtest


def _series(provider, symbol, start, end):
    cache = CACHE_DIR / f"{symbol.replace(':', '_')}__D.parquet"
    if cache.exists():
        return pd.read_parquet(cache)["close"]
    df = provider.history([symbol], start, end, "D")[symbol]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache)
    return df["close"]


def main() -> None:
    provider = FyersProvider()
    start, end = date(2021, 1, 1), date.today()
    spot = _series(provider, "NSE:NIFTY50-INDEX", start, end)
    vix = _series(provider, "NSE:INDIAVIX-INDEX", start, end)
    print(f"NIFTY + India VIX: {len(spot)} days, {spot.index[0].date()} → {spot.index[-1].date()}")
    print(f"Sizing: 1 lot (75), ~₹{MARGIN_PER_LOT:,.0f} margin/lot\n")

    variants = {
        "Naked strangle (~1SD)": dict(sd_width=1.0),
        "Strangle + 2x stop-loss": dict(sd_width=1.0, stop_mult=2.0),
        "Iron condor (1SD/2SD wings)": dict(sd_width=1.0, wing_sd=2.0),
    }
    print(f"{'strategy':<30}{'win%':>6}{'avgWin':>9}{'avgLoss':>10}{'worst':>10}"
          f"{'total':>11}{'Sharpe':>8}{'maxDD':>10}")
    print("-" * 94)
    for name, kw in variants.items():
        r = run_vol_backtest(spot, vix, hold_days=21, **kw).stats
        print(f"{name:<30}{r['win_rate']:>5.0f}%{r['avg_win']:>9,.0f}{r['avg_loss']:>10,.0f}"
              f"{r['worst_loss']:>10,.0f}{r['total_pnl']:>11,.0f}{r['sharpe']:>8.2f}{r['max_dd']:>10,.0f}")
    print(f"\n(₹ figures are per 1 lot over {len(spot)//21} monthly cycles, ~{len(spot)/252:.1f} years.)")


if __name__ == "__main__":
    main()
