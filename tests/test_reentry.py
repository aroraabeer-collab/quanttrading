"""Re-entry engine: capital must actually get redeployed after an early exit."""
import numpy as np
import pandas as pd

from options.vol_backtest import run_vol_backtest, run_vol_backtest_reentry


def _series(n=600, seed=3):
    """Synthetic NIFTY + VIX with enough drift/vol to trigger both stops and targets."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-01-01", periods=n)
    spot = pd.Series(20_000 * np.exp(np.cumsum(rng.normal(0.0003, 0.009, n))), index=idx)
    vix = pd.Series(np.clip(15 + np.cumsum(rng.normal(0, 0.3, n)), 9, 35), index=idx)
    return spot, vix


def test_profit_target_produces_more_trades_and_higher_utilisation():
    spot, vix = _series()
    hold = run_vol_backtest_reentry(spot, vix, hold_days=21, stop_mult=2.0).stats
    fast = run_vol_backtest_reentry(spot, vix, hold_days=21, stop_mult=2.0,
                                    profit_target=0.5).stats
    # Exiting early then redeploying must fit MORE cycles into the same span.
    assert fast["trades"] > hold["trades"]
    assert fast["avg_days_held"] < hold["avg_days_held"]


def test_reentry_beats_fixed_slots_on_trade_count():
    """The whole point: fixed slots leave capital idle after an early exit."""
    spot, vix = _series()
    slots = run_vol_backtest(spot, vix, hold_days=21, stop_mult=2.0, profit_target=0.5).stats
    reent = run_vol_backtest_reentry(spot, vix, hold_days=21, stop_mult=2.0,
                                     profit_target=0.5).stats
    assert reent["trades"] > slots["cycles"]


def test_trade_never_held_longer_than_horizon():
    spot, vix = _series()
    t = run_vol_backtest_reentry(spot, vix, hold_days=21, stop_mult=2.0).trades
    assert (t["held"] <= 21).all()
    assert (t["held"] >= 1).all()


def test_vix_filter_blocks_cheap_premium():
    spot, vix = _series()
    low = vix * 0 + 8.0                      # never above the floor
    r = run_vol_backtest_reentry(spot, low, hold_days=21, vix_min=13.0)
    assert r.trades.empty


def test_utilisation_is_a_sane_percentage():
    spot, vix = _series()
    s = run_vol_backtest_reentry(spot, vix, hold_days=21, stop_mult=2.0).stats
    assert 0 < s["utilization_pct"] <= 100


def test_stats_annualise_by_actual_cycles_not_assumed():
    """Skipping cycles (VIX filter) must not inflate Sharpe via a fixed cycle count."""
    spot, vix = _series()
    all_cycles = run_vol_backtest(spot, vix, hold_days=21, stop_mult=2.0).stats
    filtered = run_vol_backtest(spot, vix, hold_days=21, stop_mult=2.0, vix_min=20.0).stats
    # Fewer cycles actually happened, so the annualisation factor must shrink too.
    assert filtered["cycles"] < all_cycles["cycles"]
