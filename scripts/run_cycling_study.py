"""Does cycling capital faster increase profit?

Compares holding to expiry against taking profit early — all with **re-entry**,
so an early exit actually earns its extra cycles instead of leaving capital idle
(the flaw that made the original profit-target test unfair).

    python scripts/run_cycling_study.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root on path

import pandas as pd

from config.settings import CACHE_DIR
from options.vol_backtest import MARGIN_PER_LOT, run_vol_backtest_reentry

VARIANTS = {
    "hold to expiry": None,
    "take 25%": 0.25,
    "take 50%": 0.50,
    "take 75%": 0.75,
}


def main() -> None:
    spot = pd.read_parquet(CACHE_DIR / "NSE_NIFTY50-INDEX__D.parquet")["close"]
    vix = pd.read_parquet(CACHE_DIR / "NSE_INDIAVIX-INDEX__D.parquet")["close"]
    yrs = len(spot) / 252
    print(f"\nNIFTY + India VIX: {len(spot)} days (~{yrs:.1f} yr) · 1 lot · "
          f"₹{MARGIN_PER_LOT:,.0f} margin · stop 2x · VIX>=13 · re-entry ON\n")

    print(f"{'variant':<16}{'trades':>7}{'/yr':>6}{'win%':>6}{'ann%':>8}"
          f"{'Sharpe':>8}{'maxDD':>10}{'days':>6}{'util%':>7}{'costs':>9}")
    print("-" * 83)
    results = {}
    for name, target in VARIANTS.items():
        r = run_vol_backtest_reentry(spot, vix, hold_days=21, sd_width=1.0,
                                     stop_mult=2.0, profit_target=target,
                                     vix_min=13.0).stats
        results[name] = r
        print(f"{name:<16}{r['trades']:>7}{r['trades_per_yr']:>6.1f}{r['win_rate']:>6.0f}"
              f"{r['ann_return_pct']:>8.1f}{r['sharpe']:>8.2f}{r['max_dd']:>10,.0f}"
              f"{r['avg_days_held']:>6.1f}{r['utilization_pct']:>7.0f}{r['total_costs']:>9,.0f}")

    base = results["hold to expiry"]
    best = max(results.items(), key=lambda kv: kv[1]["sharpe"])
    print(f"\nBaseline (hold to expiry): Sharpe {base['sharpe']:.2f}, "
          f"{base['ann_return_pct']:.1f}%/yr")
    print(f"Best Sharpe: {best[0]} ({best[1]['sharpe']:.2f}, {best[1]['ann_return_pct']:.1f}%/yr)")
    if best[0] != "hold to expiry" and best[1]["ann_return_pct"] > base["ann_return_pct"]:
        print(f"→ ADOPT '{best[0]}': beats holding on BOTH Sharpe and annual return.")
    else:
        print("→ KEEP holding to expiry: no variant beats it on both metrics.")


if __name__ == "__main__":
    main()
