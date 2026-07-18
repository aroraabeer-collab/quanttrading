"""Train + evaluate the cross-sectional ML factor model (positional, daily bars).

    uv run scripts/run_ml.py [--horizon 5] [--top-k 10]

Reports out-of-sample average daily net profit (after delivery costs), the
Information Coefficient, and a naive-momentum + equal-weight benchmark.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

import numpy as np
import pandas as pd

from backtest.engine import build_panels
from config.settings import get_settings
from config.universe import universe_symbols
from data.cache import read_bars
from ml.factor_backtest import run_factor_backtest
from ml.features import build_dataset
from ml.model import feature_importance, make_ensemble, make_model, walk_forward_predict


def _load_daily_panels(universe: str):
    bars = {}
    for sym in universe_symbols(universe):
        df = read_bars(sym, "D")
        if df is not None and not df.empty:
            bars[sym] = df
    if not bars:
        raise SystemExit(
            f"No daily bars cached for {universe}. Run: "
            f"uv run scripts/download_data.py --resolution D --days 1825 --universe {universe}"
        )
    return bars, build_panels(bars)


def _naive_momentum_preds(panels, dates):
    """Benchmark 'model': rank by 6-month momentum (no ML)."""
    mom = panels.close.pct_change(126)
    return {d: mom.loc[d].dropna() for d in dates if d in mom.index}


def main() -> None:
    s = get_settings()
    p = argparse.ArgumentParser(description="ML cross-sectional factor model.")
    p.add_argument("--horizon", type=int, default=5, help="Forward-return label horizon (days).")
    p.add_argument("--top-k", type=int, default=10, help="Number of names held.")
    p.add_argument("--universe", default=s.universe, help="nifty50 or nifty200.")
    args = p.parse_args()

    bars, panels = _load_daily_panels(args.universe)
    print(f"Loaded {len(bars)} symbols, {len(panels.close)} daily bars "
          f"({panels.close.index[0].date()} → {panels.close.index[-1].date()})")

    data = build_dataset(panels, horizon=args.horizon)
    print(f"Dataset: {len(data):,} rows × {data.shape[1]-1} features\n")

    def show(name, res):
        m = res.metrics
        print(f"\n=== {name} ===")
        print(f"  OOS avg daily net profit: ₹{m['avg_daily_pnl']:,.0f}   "
              f"(on ₹{s.initial_capital:,.0f} capital)")
        print(f"  Total return:  {m['total_return_pct']:.2f}%   over {m['oos_days']} days")
        print(f"  Annualized:    {m['ann_return_pct']:.2f}%   Sharpe {m['sharpe']:.2f}")
        print(f"  Max drawdown:  {m['max_drawdown_pct']:.2f}%   "
              f"Positive days {m['pct_positive_days']:.1f}%")
        print(f"  Info Coefficient (IC): {res.ic:+.4f}")

    print("Training single GBM (walk-forward, no lookahead)…")
    preds_gbm = walk_forward_predict(data, horizon=args.horizon, model_factory=make_model)
    show("Single GBM — long-only", run_factor_backtest(panels, preds_gbm, args.horizon, args.top_k, s))

    print("\nTraining ensemble (GBM + ExtraTrees + Ridge, rank-blended)…")
    preds_ens = walk_forward_predict(data, horizon=args.horizon, model_factory=make_ensemble)
    show("Ensemble — long-only", run_factor_backtest(panels, preds_ens, args.horizon, args.top_k, s))
    show("Ensemble — long-SHORT (market-neutral)",
         run_factor_backtest(panels, preds_ens, args.horizon, args.top_k, s, long_short=True))

    naive = _naive_momentum_preds(panels, list(preds_ens.keys()))
    show("Benchmark: 6M momentum (no ML)", run_factor_backtest(panels, naive, args.horizon, args.top_k, s))

    print("\n=== Feature importance (permutation, in-sample) ===")
    for feat, imp in feature_importance(data, args.horizon).items():
        print(f"  {feat:<12} {imp:+.5f}")


if __name__ == "__main__":
    main()
